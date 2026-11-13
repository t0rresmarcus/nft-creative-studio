from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import assert_can_create_project, get_current_user, get_db, record_usage, require_project
from app.models import (
    Approval,
    Asset,
    Collection,
    Comment,
    EditHistory,
    ExportRecord,
    NFTItem,
    Project,
    ProjectMember,
    Trait,
    TraitCategory,
    TraitRule,
    User,
    Workflow,
)
from app.schemas import CommentIn, DecisionIn, MemberIn, ProjectIn, ProjectUpdate
from app.security import utcnow
from app.serializers import comment_out, project_out, user_out
from app.services.cleanup import delete_project

router = APIRouter(prefix="/api")

PROJECT_TYPES = {"single", "edition", "generative", "photo"}
LICENSES = {"cc0", "cc-by", "commercial", "custom"}


def _counts(db: Session, project_id: str) -> tuple[int, int]:
    return (
        db.query(Asset).filter_by(project_id=project_id).count(),
        db.query(Collection).filter_by(project_id=project_id).count(),
    )


@router.get("/projects")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned = db.query(Project).filter_by(owner_id=user.id).all()
    member_rows = db.query(ProjectMember).filter_by(user_id=user.id).all()
    shared = [db.get(Project, row.project_id) for row in member_rows]
    projects = []
    seen = set()
    for project in [*owned, *shared]:
        if project is None or project.id in seen:
            continue
        seen.add(project.id)
        role = "owner" if project.owner_id == user.id else next(row.role for row in member_rows if row.project_id == project.id)
        assets, collections = _counts(db, project.id)
        projects.append(project_out(project, role, assets, collections))
    projects.sort(key=lambda item: item["updated_at"] or "", reverse=True)
    return projects


@router.post("/projects")
def create_project(body: ProjectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.project_type not in PROJECT_TYPES:
        raise HTTPException(status_code=400, detail="Project type must be single, edition, generative, or photo")
    if body.license not in LICENSES:
        raise HTTPException(status_code=400, detail="License must be cc0, cc-by, commercial, or custom")
    if body.canvas_width < 32 or body.canvas_height < 32 or body.canvas_width > 4096 or body.canvas_height > 4096:
        raise HTTPException(status_code=400, detail="Canvas size must be between 32 and 4096")
    assert_can_create_project(db, user)
    project = Project(
        owner_id=user.id,
        name=body.name.strip(),
        description=body.description.strip(),
        project_type=body.project_type,
        canvas_width=body.canvas_width,
        canvas_height=body.canvas_height,
        license=body.license,
        ai_disclosure=body.ai_disclosure.strip(),
    )
    db.add(project)
    record_usage(db, user, "project", 1, detail=project.name)
    db.commit()
    db.refresh(project)
    return project_out(project, "owner", 0, 0)


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, role = require_project(db, user, project_id)
    assets, collections = _counts(db, project.id)
    return project_out(project, role, assets, collections)


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, role = require_project(db, user, project_id, "editor")
    data = body.model_dump(exclude_unset=True)
    if "project_type" in data and data["project_type"] not in PROJECT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown project type")
    if "license" in data and data["license"] not in LICENSES:
        raise HTTPException(status_code=400, detail="Unknown license")
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(project, key, value)
    project.updated_at = utcnow()
    db.commit()
    assets, collections = _counts(db, project.id)
    return project_out(project, role, assets, collections)


@router.delete("/projects/{project_id}")
def remove_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "owner")
    delete_project(db, project)
    return {"ok": True}


@router.get("/projects/{project_id}/checklist")
def checklist(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id)
    asset_ids = [row[0] for row in db.query(Asset.id).filter_by(project_id=project.id).all()]
    edits = db.query(EditHistory).filter(EditHistory.asset_id.in_(asset_ids)).count() if asset_ids else 0
    categories = db.query(TraitCategory).filter_by(project_id=project.id).count()
    rules = db.query(TraitRule).filter_by(project_id=project.id).count()
    weighted = db.query(Trait).filter(Trait.project_id == project.id, Trait.weight != 1).count()
    workflows = db.query(Workflow).filter_by(project_id=project.id).count()
    collections = db.query(Collection).filter_by(project_id=project.id).all()
    collection_ids = [collection.id for collection in collections]
    items = db.query(NFTItem).filter(NFTItem.collection_id.in_(collection_ids)).count() if collection_ids else 0
    rendered = (
        db.query(NFTItem).filter(NFTItem.collection_id.in_(collection_ids), NFTItem.image_asset_id.isnot(None)).count()
        if collection_ids
        else 0
    )
    report_ok = any((collection.last_report or {}).get("status") == "pass" for collection in collections)
    zip_export = db.query(ExportRecord).filter_by(project_id=project.id, kind="zip").count()
    ipfs_export = db.query(ExportRecord).filter_by(project_id=project.id, kind="ipfs").count()
    steps = [
        ("project", "Create an NFT project", True),
        ("assets", "Upload artwork and source assets", bool(asset_ids)),
        ("edit", "Edit artwork", edits > 0),
        ("traits", "Organize layers and trait categories", categories > 0),
        ("rarity", "Configure rarity and compatibility rules", rules > 0 or weighted > 0),
        ("workflow", "Configure batch-processing workflows", workflows > 0),
        ("generate", "Generate the NFT collection", items > 0),
        ("validate", "Validate uniqueness and rarity", report_ok),
        ("review", "Review individual artwork", rendered > 0),
        ("metadata", "Generate metadata", items > 0),
        ("export", "Export collection files", zip_export > 0),
        ("ipfs", "Upload assets for distribution", ipfs_export > 0),
        ("market", "Prepare marketplace publishing", report_ok and zip_export > 0),
    ]
    return [{"id": step_id, "label": label, "done": done} for step_id, label, done in steps]


@router.get("/projects/{project_id}/members")
def list_members(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id)
    owner = db.get(User, project.owner_id)
    members = [{"user_id": owner.id, "email": owner.email, "name": owner.name, "role": "owner", "id": None}]
    for row in db.query(ProjectMember).filter_by(project_id=project.id).all():
        person = db.get(User, row.user_id)
        members.append(
            {"id": row.id, "user_id": row.user_id, "email": person.email if person else "", "name": person.name if person else "", "role": row.role}
        )
    return members


@router.post("/projects/{project_id}/members")
def add_member(project_id: str, body: MemberIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "owner")
    if body.role not in {"editor", "reviewer"}:
        raise HTTPException(status_code=400, detail="Role must be editor or reviewer")
    person = db.query(User).filter_by(email=body.email.strip().lower()).one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="That person needs an account before they can be added")
    if person.id == project.owner_id:
        raise HTTPException(status_code=400, detail="The owner is already on the project")
    existing = db.query(ProjectMember).filter_by(project_id=project.id, user_id=person.id).one_or_none()
    if existing:
        existing.role = body.role
        db.commit()
        return {"id": existing.id, "role": existing.role}
    member = ProjectMember(project_id=project.id, user_id=person.id, role=body.role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return {"id": member.id, "role": member.role, "email": person.email, "name": person.name}


@router.delete("/projects/{project_id}/members/{member_id}")
def remove_member(project_id: str, member_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "owner")
    member = db.get(ProjectMember, member_id)
    if member is None or member.project_id != project.id:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.commit()
    return {"ok": True}


@router.get("/projects/{project_id}/comments")
def list_comments(project_id: str, item_id: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id)
    query = db.query(Comment).filter_by(project_id=project.id)
    if item_id:
        query = query.filter_by(item_id=item_id)
    rows = query.order_by(Comment.created_at.asc()).all()
    return [comment_out(row, db.get(User, row.user_id)) for row in rows]


@router.post("/projects/{project_id}/comments")
def add_comment(project_id: str, body: CommentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id)
    if body.item_id:
        item = db.get(NFTItem, body.item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Token not found")
    comment = Comment(project_id=project.id, item_id=body.item_id, user_id=user.id, body=body.body.strip())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment_out(comment, user)


@router.post("/items/{item_id}/decision")
def decide(item_id: str, body: DecisionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(NFTItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Token not found")
    collection = db.get(Collection, item.collection_id)
    require_project(db, user, collection.project_id, "reviewer")
    if body.status not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Status must be approved or rejected")
    approval = db.query(Approval).filter_by(item_id=item.id, user_id=user.id).one_or_none()
    if approval is None:
        approval = Approval(item_id=item.id, user_id=user.id, status=body.status)
        db.add(approval)
    else:
        approval.status = body.status
        approval.created_at = utcnow()
    db.commit()
    return {"status": approval.status}
