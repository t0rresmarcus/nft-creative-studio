from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_project
from app.models import Asset, Trait, TraitCategory, TraitRule, TraitTemplate, User
from app.schemas import CategoryIn, CategoryUpdate, OrderIn, PreviewIn, RuleIn, TemplateIn, TraitUpdate
from app.security import utcnow
from app.serializers import asset_out, category_out, rule_out, trait_out
from app.services.collections import load_graph, render_selection_image
from app.services.generator import GenerationError, generate
from app.services.library import apply_trait_template, build_sample_layers, snapshot_traits, store_image, store_upload

router = APIRouter(prefix="/api")


def _graph_payload(db: Session, project_id: str) -> dict:
    categories = db.query(TraitCategory).filter_by(project_id=project_id).order_by(TraitCategory.z_index, TraitCategory.id).all()
    traits = db.query(Trait).filter_by(project_id=project_id).all()
    rules = db.query(TraitRule).filter_by(project_id=project_id).all()
    payload = []
    for category in categories:
        rows = []
        for trait in sorted((trait for trait in traits if trait.category_id == category.id), key=lambda item: item.name.lower()):
            asset = db.get(Asset, trait.asset_id) if trait.asset_id else None
            rows.append(trait_out(trait, asset))
        payload.append(category_out(category, rows))
    return {"categories": payload, "rules": [rule_out(rule) for rule in rules]}


@router.get("/projects/{project_id}/traits")
def trait_graph(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id)
    return _graph_payload(db, project.id)


@router.post("/projects/{project_id}/categories")
def create_category(project_id: str, body: CategoryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    z_index = db.query(TraitCategory).filter_by(project_id=project.id).count() * 10
    category = TraitCategory(project_id=project.id, name=body.name.strip(), z_index=z_index, optional=body.optional, none_weight=body.none_weight)
    db.add(category)
    project.updated_at = utcnow()
    db.commit()
    db.refresh(category)
    return category_out(category, [])


@router.patch("/categories/{category_id}")
def update_category(category_id: str, body: CategoryUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    category = db.get(TraitCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Layer not found")
    require_project(db, user, category.project_id, "editor")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(category, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    return _graph_payload(db, category.project_id)


@router.delete("/categories/{category_id}")
def delete_category(category_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    category = db.get(TraitCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Layer not found")
    require_project(db, user, category.project_id, "editor")
    trait_ids = [row[0] for row in db.query(Trait.id).filter_by(category_id=category.id).all()]
    if trait_ids:
        db.query(TraitRule).filter(or_(TraitRule.trait_a_id.in_(trait_ids), TraitRule.trait_b_id.in_(trait_ids))).delete(synchronize_session=False)
        db.query(Trait).filter(Trait.id.in_(trait_ids)).delete(synchronize_session=False)
    db.delete(category)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/categories/order")
def order_categories(project_id: str, body: OrderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    for index, category_id in enumerate(body.ids):
        category = db.get(TraitCategory, category_id)
        if category and category.project_id == project.id:
            category.z_index = index * 10
    db.commit()
    return _graph_payload(db, project.id)


@router.post("/categories/{category_id}/traits")
async def create_trait(
    category_id: str,
    name: str = Form(...),
    weight: float = Form(1),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = db.get(TraitCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Layer not found")
    require_project(db, user, category.project_id, "editor")
    data = await file.read()
    try:
        asset = store_upload(db, project_id=category.project_id, user_id=user.id, data=data, name=file.filename or f"{name}.png", kind="trait")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Trait artwork must be an image") from exc
    trait = Trait(project_id=category.project_id, category_id=category.id, asset_id=asset.id, name=name.strip(), weight=weight)
    db.add(trait)
    db.commit()
    db.refresh(trait)
    return trait_out(trait, asset)


@router.patch("/traits/{trait_id}")
def update_trait(trait_id: str, body: TraitUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    trait = db.get(Trait, trait_id)
    if trait is None:
        raise HTTPException(status_code=404, detail="Trait not found")
    require_project(db, user, trait.project_id, "editor")
    data = body.model_dump(exclude_unset=True)
    if data.get("clear_exact_count"):
        trait.exact_count = None
    data.pop("clear_exact_count", None)
    for key, value in data.items():
        setattr(trait, key, value.strip() if isinstance(value, str) else value)
    if trait.weight < 0:
        raise HTTPException(status_code=400, detail="Weight cannot be negative")
    db.commit()
    asset = db.get(Asset, trait.asset_id) if trait.asset_id else None
    return trait_out(trait, asset)


@router.delete("/traits/{trait_id}")
def delete_trait(trait_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    trait = db.get(Trait, trait_id)
    if trait is None:
        raise HTTPException(status_code=404, detail="Trait not found")
    require_project(db, user, trait.project_id, "editor")
    db.query(TraitRule).filter((TraitRule.trait_a_id == trait.id) | (TraitRule.trait_b_id == trait.id)).delete(synchronize_session=False)
    db.delete(trait)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/rules")
def create_rule(project_id: str, body: RuleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    if body.rule_type not in {"exclude", "require"}:
        raise HTTPException(status_code=400, detail="Rule type must be exclude or require")
    left = db.get(Trait, body.trait_a_id)
    right = db.get(Trait, body.trait_b_id)
    if left is None or right is None or left.project_id != project.id or right.project_id != project.id:
        raise HTTPException(status_code=404, detail="Choose two traits from this project")
    if left.category_id == right.category_id:
        raise HTTPException(status_code=400, detail="Rules must connect traits from different layers")
    rule = TraitRule(project_id=project.id, rule_type=body.rule_type, trait_a_id=left.id, trait_b_id=right.id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule_out(rule)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.get(TraitRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    require_project(db, user, rule.project_id, "editor")
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/traits/sample")
def sample_traits(project_id: str, replace: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    try:
        count = build_sample_layers(db, project, user.id, replace=replace)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"created": count, **_graph_payload(db, project.id)}


@router.post("/projects/{project_id}/traits/preview")
def preview_traits(project_id: str, body: PreviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    categories, traits, rules, trait_map, category_map = load_graph(db, project.id)
    try:
        if body.trait_ids:
            selection: dict[str, str | None] = {category.id: None for category in category_map.values()}
            for trait_id in body.trait_ids:
                trait = trait_map.get(trait_id)
                if trait is None:
                    raise HTTPException(status_code=404, detail="Trait not found")
                selection[trait.category_id] = trait.id
        else:
            result = generate(categories, traits, rules, 1, 1, "weighted")
            selection = result.tokens[0].selection
        image, warnings = render_selection_image(db, project, selection)
    except GenerationError as exc:
        raise HTTPException(status_code=422, detail={"message": exc.message, "suggestions": exc.suggestions}) from exc
    asset = store_image(db, project_id=project.id, user_id=user.id, image=image, name="preview", kind="preview")
    db.commit()
    return {"asset": asset_out(asset), "warnings": warnings}


@router.post("/projects/{project_id}/trait-templates")
def save_template(project_id: str, body: TemplateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    template = TraitTemplate(user_id=user.id, name=body.name.strip(), payload=snapshot_traits(db, project.id))
    db.add(template)
    db.commit()
    db.refresh(template)
    return {"id": template.id, "name": template.name}


@router.get("/trait-templates")
def list_templates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(TraitTemplate).filter_by(user_id=user.id).order_by(TraitTemplate.created_at.desc()).all()
    return [{"id": row.id, "name": row.name, "created_at": row.created_at.isoformat()} for row in rows]


@router.post("/projects/{project_id}/trait-templates/{template_id}/apply")
def apply_template(project_id: str, template_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    template = db.get(TraitTemplate, template_id)
    if template is None or template.user_id != user.id:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        apply_trait_template(db, project, user.id, template.payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _graph_payload(db, project.id)
