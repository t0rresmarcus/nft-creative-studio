from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user, get_db, require_project
from app.models import Asset, EditHistory, User
from app.schemas import EditorIn
from app.security import verify_asset_signature
from app.serializers import asset_out
from app.services.imaging import ImageError
from app.services.library import render_edit, store_upload
from app.storage import open_image

router = APIRouter(prefix="/api")


@router.get("/files/{asset_id}")
def read_file(asset_id: str, variant: str = "full", expires: int = 0, signature: str = "", db: Session = Depends(get_db)):
    if not verify_asset_signature(asset_id, variant, expires, signature):
        raise HTTPException(status_code=403, detail="This image link has expired. Refresh the page.")
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Image not found")
    key = asset.thumb_key if variant == "thumb" and asset.thumb_key else asset.storage_key
    path = settings.storage_path / key
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file is missing")
    media = "image/png" if variant == "thumb" else asset.mime
    return FileResponse(path, media_type=media)


@router.get("/content/{digest}")
def read_content(digest: str):
    from app.services.ipfs import find_blob

    path = find_blob(digest)
    if path is None:
        raise HTTPException(status_code=404, detail="Content not found")
    media = "application/json" if path.suffix == ".json" else "image/png"
    return FileResponse(path, media_type=media)


@router.get("/projects/{project_id}/assets")
def list_assets(project_id: str, kind: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id)
    query = db.query(Asset).filter_by(project_id=project.id)
    if kind:
        query = query.filter_by(kind=kind)
    assets = query.order_by(Asset.created_at.desc()).all()
    return [asset_out(asset) for asset in assets]


@router.post("/projects/{project_id}/assets")
async def upload_assets(
    project_id: str,
    files: list[UploadFile] = File(...),
    kind: str = "source",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project, _role = require_project(db, user, project_id, "editor")
    if kind not in {"source", "trait", "reference"}:
        kind = "source"
    stored = []
    limit = settings.max_upload_mb * 1024 * 1024
    for upload in files:
        data = await upload.read()
        if len(data) > limit:
            raise HTTPException(status_code=413, detail=f"{upload.filename} is larger than {settings.max_upload_mb} MB")
        try:
            open_image(data)
            asset = store_upload(db, project_id=project.id, user_id=user.id, data=data, name=upload.filename or "image.png", kind=kind)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{upload.filename or 'file'} is not a supported image") from exc
        stored.append(asset_out(asset))
    project.updated_at = project.updated_at
    db.commit()
    return stored


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Image not found")
    require_project(db, user, asset.project_id, "editor")
    db.query(EditHistory).filter_by(asset_id=asset.id).delete()
    db.delete(asset)
    db.commit()
    return {"ok": True}


@router.post("/assets/{asset_id}/render")
def render_asset(asset_id: str, body: EditorIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Image not found")
    require_project(db, user, asset.project_id, "editor")
    try:
        result = render_edit(
            db,
            project_id=asset.project_id,
            user_id=user.id,
            asset=asset,
            operations=body.operations,
            layers=body.layers,
        )
    except (ImageError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return asset_out(result)


@router.get("/assets/{asset_id}/history")
def asset_history(asset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Image not found")
    require_project(db, user, asset.project_id)
    history = db.query(EditHistory).filter_by(asset_id=asset.id).order_by(EditHistory.created_at.asc()).all()
    versions = db.query(Asset).filter_by(parent_asset_id=asset.id).order_by(Asset.created_at.asc()).all()
    return {
        "edits": [
            {
                "id": row.id,
                "operations": row.operations,
                "note": row.note,
                "result_asset_id": row.result_asset_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in history
        ],
        "versions": [asset_out(row) for row in versions],
    }
