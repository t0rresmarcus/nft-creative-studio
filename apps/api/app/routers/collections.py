from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.deps import assert_supply, get_current_user, get_db, record_usage, require_project
from app.models import Collection, MetadataRecord, NFTAttribute, NFTItem, Project, User
from app.schemas import CollectionIn
from app.security import utcnow
from app.serializers import collection_out, item_out, job_out
from app.services.collections import assess_collection, plan_collection, regenerate_item, refresh_metadata
from app.services.exporting import build_zip, collection_rows
from app.services.generator import GenerationError
from app.services.jobs import create_job, enqueue
from app.services.metadata import PROFILES, metadata_to_csv

router = APIRouter(prefix="/api")


def _items(db: Session, collection: Collection) -> list[dict]:
    items = db.query(NFTItem).filter_by(collection_id=collection.id).order_by(NFTItem.token_id).all()
    payload = []
    for item in items:
        attributes = [
            {"trait_type": row.trait_type, "value": row.value}
            for row in db.query(NFTAttribute).filter_by(item_id=item.id).all()
        ]
        record = db.query(MetadataRecord).filter_by(item_id=item.id).one_or_none()
        payload.append(item_out(item, attributes, record.body if record else None))
    return payload


def _owned_collection(db: Session, user: User, collection_id: str, min_role: str = "reviewer") -> tuple[Collection, Project]:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    project, _role = require_project(db, user, collection.project_id, min_role)
    return collection, project


@router.get("/marketplace-profiles")
def profiles():
    return list(PROFILES.values())


@router.get("/projects/{project_id}/collections")
def list_collections(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id)
    rows = db.query(Collection).filter_by(project_id=project.id).order_by(Collection.created_at.desc()).all()
    return [collection_out(row) for row in rows]


@router.post("/projects/{project_id}/collections")
def create_collection(project_id: str, body: CollectionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    if body.mode not in {"weighted", "exact"}:
        raise HTTPException(status_code=400, detail="Mode must be weighted or exact")
    if body.metadata_schema not in {"erc721", "metaplex"}:
        raise HTTPException(status_code=400, detail="Schema must be erc721 or metaplex")
    if body.marketplace_profile not in PROFILES:
        raise HTTPException(status_code=400, detail="Unknown marketplace profile")
    assert_supply(user, body.supply)
    collection = Collection(
        project_id=project.id,
        name=body.name.strip(),
        supply=body.supply,
        seed=body.seed,
        mode=body.mode,
        description_template=body.description_template,
        image_base_uri=body.image_base_uri.strip(),
        external_url=body.external_url.strip(),
        symbol=body.symbol.strip(),
        metadata_schema=body.metadata_schema,
        marketplace_profile=body.marketplace_profile,
    )
    db.add(collection)
    record_usage(db, user, "collection", 1, project.id, collection.name)
    db.commit()
    db.refresh(collection)
    return collection_out(collection)


@router.get("/collections/{collection_id}")
def get_collection(collection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, _project = _owned_collection(db, user, collection_id)
    return {**collection_out(collection), "report": collection.last_report, "items": _items(db, collection)}


@router.patch("/collections/{collection_id}")
def update_collection(collection_id: str, body: CollectionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, project = _owned_collection(db, user, collection_id, "editor")
    assert_supply(user, body.supply)
    collection.name = body.name.strip()
    collection.supply = body.supply
    collection.seed = body.seed
    collection.mode = body.mode
    collection.description_template = body.description_template
    collection.image_base_uri = body.image_base_uri.strip()
    collection.external_url = body.external_url.strip()
    collection.symbol = body.symbol.strip()
    collection.metadata_schema = body.metadata_schema
    collection.marketplace_profile = body.marketplace_profile
    collection.updated_at = utcnow()
    if db.query(NFTItem).filter_by(collection_id=collection.id).count():
        refresh_metadata(db, collection, project)
    db.commit()
    return collection_out(collection)


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, _project = _owned_collection(db, user, collection_id, "editor")
    from app.services.collections import clear_items

    clear_items(db, collection.id)
    db.delete(collection)
    db.commit()
    return {"ok": True}


@router.post("/collections/{collection_id}/plan")
def plan(collection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, project = _owned_collection(db, user, collection_id, "editor")
    assert_supply(user, collection.supply)
    try:
        report = plan_collection(db, collection, project)
    except GenerationError as exc:
        raise HTTPException(status_code=422, detail={"message": exc.message, "suggestions": exc.suggestions}) from exc
    record_usage(db, user, "plan", collection.supply, project.id)
    db.commit()
    return {"collection": collection_out(collection), "report": report, "items": _items(db, collection)}


@router.post("/collections/{collection_id}/render")
def render(collection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, project = _owned_collection(db, user, collection_id, "editor")
    job = create_job(db, project_id=project.id, user_id=user.id, kind="render_collection", payload={"collection_id": collection.id})
    job = enqueue(db, job)
    record_usage(db, user, "render", collection.supply, project.id)
    db.commit()
    return job_out(job)


@router.post("/collections/{collection_id}/items/{item_id}/regenerate")
def regenerate(collection_id: str, item_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, project = _owned_collection(db, user, collection_id, "editor")
    item = db.get(NFTItem, item_id)
    if item is None or item.collection_id != collection.id:
        raise HTTPException(status_code=404, detail="Token not found")
    try:
        regenerate_item(db, collection, project, item)
    except GenerationError as exc:
        raise HTTPException(status_code=422, detail={"message": exc.message, "suggestions": exc.suggestions}) from exc
    return next(row for row in _items(db, collection) if row["id"] == item.id)


@router.get("/collections/{collection_id}/metadata")
def metadata(collection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, _project = _owned_collection(db, user, collection_id)
    return collection_rows(db, collection)


@router.get("/collections/{collection_id}/metadata.csv")
def metadata_csv(collection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, _project = _owned_collection(db, user, collection_id)
    text = metadata_to_csv(collection_rows(db, collection))
    return Response(content=text, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{collection.name}.csv"'})


@router.get("/collections/{collection_id}/report")
def report(collection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, project = _owned_collection(db, user, collection_id)
    fresh = assess_collection(db, collection, project)
    collection.last_report = fresh
    db.commit()
    return fresh


@router.post("/collections/{collection_id}/export")
def export_zip(collection_id: str, force: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, project = _owned_collection(db, user, collection_id, "editor")
    payload, _report = build_zip(db, collection, project, user.id, force=force)
    filename = "".join(character if character.isalnum() or character in "-_" else "-" for character in collection.name) or "collection"
    return Response(content=payload, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}.zip"'})


@router.post("/collections/{collection_id}/ipfs")
def ipfs(collection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    collection, project = _owned_collection(db, user, collection_id, "editor")
    job = create_job(db, project_id=project.id, user_id=user.id, kind="ipfs", payload={"collection_id": collection.id})
    job = enqueue(db, job)
    return job_out(job)
