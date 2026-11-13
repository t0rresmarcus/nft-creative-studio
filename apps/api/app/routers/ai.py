from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import charge_credits, get_current_user, get_db, plan_limits, require_project
from app.models import Asset, User
from app.schemas import AiBatchIn, EnhanceIn, InpaintIn, RemoveBgIn, VariationIn
from app.serializers import asset_out
from app.services.imaging import ImageError, enhance, inpaint_rect, remove_background, replace_background, resize_image, sharpen, variations
from app.services.library import load_asset_image, store_image

router = APIRouter(prefix="/api")


def _load(db: Session, user: User, asset_id: str, min_role: str = "editor") -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Image not found")
    require_project(db, user, asset.project_id, min_role)
    return asset


def _guard_ai(user: User, mode: str) -> None:
    if mode == "ai" and not plan_limits(user)["ai"]:
        raise HTTPException(status_code=402, detail="AI operations are included with Creator, Pro, and Studio")


@router.post("/assets/{asset_id}/remove-background")
def remove_bg(asset_id: str, body: RemoveBgIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = _load(db, user, asset_id)
    _guard_ai(user, body.mode)
    image = load_asset_image(asset)
    try:
        if body.replacement_color:
            result, method = replace_background(image, body.replacement_color, body.tolerance, body.mode)
        else:
            result, method = remove_background(image, body.tolerance, body.mode)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    if method in {"remote", "rembg"}:
        charge_credits(db, user, 1, "background", asset.project_id, method)
    stored = store_image(db, project_id=asset.project_id, user_id=user.id, image=result, name=f"{asset.original_name}-cut", kind="render", parent_asset_id=asset.id)
    db.commit()
    return {"asset": asset_out(stored), "method": method}


@router.post("/assets/{asset_id}/enhance")
def enhance_asset(asset_id: str, body: EnhanceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = _load(db, user, asset_id)
    _guard_ai(user, "ai")
    image = load_asset_image(asset)
    scale = min(max(body.scale, 1), 4)
    sharpened = sharpen(enhance(image, "contrast", 1.08))
    if scale > 1:
        sharpened = resize_image(sharpened, sharpened.width * scale, sharpened.height * scale, "exact")
    charge_credits(db, user, 1, "enhance", asset.project_id, f"{scale}x")
    stored = store_image(db, project_id=asset.project_id, user_id=user.id, image=sharpened, name=f"{asset.original_name}-enhanced", kind="render", parent_asset_id=asset.id)
    db.commit()
    return asset_out(stored)


@router.post("/assets/{asset_id}/inpaint")
def inpaint_asset(asset_id: str, body: InpaintIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = _load(db, user, asset_id)
    image = load_asset_image(asset)
    try:
        result = inpaint_rect(image, body.x, body.y, body.width, body.height)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    stored = store_image(db, project_id=asset.project_id, user_id=user.id, image=result, name=f"{asset.original_name}-cleaned", kind="render", parent_asset_id=asset.id)
    db.commit()
    return asset_out(stored)


@router.post("/assets/{asset_id}/variations")
def vary(asset_id: str, body: VariationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = _load(db, user, asset_id)
    image = load_asset_image(asset)
    count = min(max(body.count, 1), 8)
    charge_credits(db, user, count, "variations", asset.project_id)
    stored = []
    for index, variant in enumerate(variations(image, count, body.seed)):
        saved = store_image(
            db,
            project_id=asset.project_id,
            user_id=user.id,
            image=variant,
            name=f"{asset.original_name}-var-{index + 1}",
            kind="variation",
            parent_asset_id=asset.id,
        )
        stored.append(asset_out(saved))
    db.commit()
    return stored


@router.post("/projects/{project_id}/ai/batch")
def ai_batch(project_id: str, body: AiBatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Run one image operation across a selection. Stored as a one-step workflow job."""
    from app.models import Workflow

    project, _role = require_project(db, user, project_id, "editor")
    if body.operation not in {"remove_background", "sharpen", "resize", "brightness", "contrast", "replace_background"}:
        raise HTTPException(status_code=400, detail="Unsupported batch operation")
    workflow = Workflow(project_id=project.id, name=f"AI batch {body.operation}", operations=[{"type": body.operation, "params": body.params}])
    db.add(workflow)
    db.flush()
    from app.services.jobs import create_job, enqueue
    from app.serializers import job_out

    job = create_job(
        db,
        project_id=project.id,
        user_id=user.id,
        kind="batch",
        payload={"workflow_id": workflow.id, "asset_ids": body.asset_ids, "seed": 1, "dry_run": False},
    )
    return job_out(enqueue(db, job))
