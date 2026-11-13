"""Upload storage, sample layers, and editor rendering."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from app.models import Asset, EditHistory, Trait, TraitCategory, TraitRule, new_id
from app.security import utcnow
from app.services.imaging import composite, run_operations
from app.storage import image_to_png, make_thumbnail, open_image, read_bytes, write_bytes


def safe_stem(name: str) -> str:
    stem = name.rsplit(".", 1)[0]
    cleaned = "".join(character if character.isalnum() or character in "-_" else "-" for character in stem).strip("-")
    return (cleaned or "image")[:80]


def store_image(
    db: Session,
    *,
    project_id: str,
    user_id: str | None,
    image: Image.Image,
    name: str,
    kind: str,
    parent_asset_id: str | None = None,
) -> Asset:
    payload = image_to_png(image)
    key, digest = write_bytes(payload, ".png")
    thumb_key, _ = write_bytes(make_thumbnail(image), ".png")
    asset = Asset(
        id=new_id(),
        project_id=project_id,
        parent_asset_id=parent_asset_id,
        filename=f"{safe_stem(name)}.png",
        original_name=f"{safe_stem(name)}.png",
        mime="image/png",
        size=len(payload),
        width=image.width,
        height=image.height,
        sha256=digest,
        storage_key=key,
        thumb_key=thumb_key,
        kind=kind,
        created_by=user_id,
        created_at=utcnow(),
    )
    db.add(asset)
    db.flush()
    return asset


def store_upload(
    db: Session,
    *,
    project_id: str,
    user_id: str | None,
    data: bytes,
    name: str,
    kind: str,
) -> Asset:
    image = open_image(data)
    if image.width > 8000 or image.height > 8000:
        raise ValueError("Images must be 8000 pixels or smaller on each side")
    suffix = ".png"
    mime = "image/png"
    image_format = (image.format or "PNG").upper()
    if image_format in {"JPEG", "JPG"}:
        suffix, mime = ".jpg", "image/jpeg"
    elif image_format == "WEBP":
        suffix, mime = ".webp", "image/webp"
    elif image_format == "GIF":
        suffix, mime = ".gif", "image/gif"
    key, digest = write_bytes(data, suffix)
    thumb_key, _ = write_bytes(make_thumbnail(image), ".png")
    asset = Asset(
        project_id=project_id,
        filename=f"{safe_stem(name)}{suffix}",
        original_name=name,
        mime=mime,
        size=len(data),
        width=image.width,
        height=image.height,
        sha256=digest,
        storage_key=key,
        thumb_key=thumb_key,
        kind=kind,
        created_by=user_id,
    )
    db.add(asset)
    db.flush()
    return asset


def load_asset_image(asset: Asset) -> Image.Image:
    return open_image(read_bytes(asset.storage_key))


def render_edit(
    db: Session,
    *,
    project_id: str,
    user_id: str,
    asset: Asset,
    operations: list[dict],
    layers: list[dict],
) -> Asset:
    image = load_asset_image(asset)
    image, _notes = run_operations(image, operations, seed=1, filename=asset.original_name)
    if layers:
        stack = [{"image": image, "x": 0, "y": 0, "scale": 1, "opacity": 1}]
        for layer in layers:
            other = db.get(Asset, layer["asset_id"])
            if other is None or other.project_id != project_id:
                raise ValueError("A layer points at an asset from another project")
            stack.append(
                {
                    "image": load_asset_image(other),
                    "x": layer.get("x", 0),
                    "y": layer.get("y", 0),
                    "scale": layer.get("scale", 1),
                    "opacity": layer.get("opacity", 1),
                }
            )
        image = composite(image.size, stack)
    result = store_image(
        db,
        project_id=project_id,
        user_id=user_id,
        image=image,
        name=f"{safe_stem(asset.original_name)}-edit",
        kind="render",
        parent_asset_id=asset.id,
    )
    db.add(
        EditHistory(
            asset_id=asset.id,
            user_id=user_id,
            operations={"operations": operations, "layers": layers},
            note="editor",
            result_asset_id=result.id,
        )
    )
    return result


def _canvas(width: int, height: int, color: tuple[int, int, int, int] | None = None) -> Image.Image:
    return Image.new("RGBA", (width, height), color or (0, 0, 0, 0))


def _sample_art(kind: str, width: int, height: int, color: tuple[int, int, int, int]) -> Image.Image:
    image = _canvas(width, height)
    draw = ImageDraw.Draw(image)
    if kind == "background":
        draw.rectangle((0, 0, width, height), fill=color)
        return image
    if kind == "round":
        draw.ellipse((width * 0.28, height * 0.22, width * 0.72, height * 0.78), fill=color)
    elif kind == "block":
        draw.rounded_rectangle((width * 0.26, height * 0.24, width * 0.74, height * 0.8), radius=int(width * 0.06), fill=color)
    elif kind == "diamond":
        cx, cy = width / 2, height * 0.5
        draw.polygon([(cx, cy - height * 0.28), (cx + width * 0.22, cy), (cx, cy + height * 0.28), (cx - width * 0.22, cy)], fill=color)
    elif kind == "dots":
        r = width * 0.035
        for cx in (0.42, 0.58):
            draw.ellipse((width * cx - r, height * 0.44 - r, width * cx + r, height * 0.44 + r), fill=color)
    elif kind == "line":
        draw.rectangle((width * 0.36, height * 0.43, width * 0.46, height * 0.46), fill=color)
        draw.rectangle((width * 0.54, height * 0.43, width * 0.64, height * 0.46), fill=color)
    elif kind == "wide":
        r = width * 0.05
        for cx in (0.40, 0.60):
            draw.ellipse((width * cx - r, height * 0.42 - r * 0.6, width * cx + r, height * 0.42 + r * 0.6), fill=color)
    elif kind == "star":
        cx, cy = width * 0.5, height * 0.16
        points = []
        for index in range(10):
            radius = width * (0.07 if index % 2 == 0 else 0.03)
            angle = -3.14159 / 2 + index * 3.14159 / 5
            points.append((cx + radius * __import__("math").cos(angle), cy + radius * __import__("math").sin(angle)))
        draw.polygon(points, fill=color)
    elif kind == "ring":
        draw.ellipse((width * 0.38, height * 0.08, width * 0.62, height * 0.28), outline=color, width=max(4, width // 80))
    elif kind == "dash":
        draw.rectangle((width * 0.38, height * 0.14, width * 0.62, height * 0.18), fill=color)
    return image


SAMPLE_LAYERS = [
    (
        "Background",
        False,
        0,
        [
            ("Dusk", (28, 26, 24, 255), "background", 1, ""),
            ("Citrus", (255, 90, 54, 255), "background", 1, ""),
            ("Noir", (12, 12, 11, 255), "background", 1, ""),
            ("Salt", (246, 241, 231, 255), "background", 1, ""),
        ],
    ),
    (
        "Figure",
        False,
        10,
        [
            ("Round", (232, 196, 160, 255), "round", 1, ""),
            ("Block", (88, 168, 158, 255), "block", 1, ""),
            ("Diamond", (246, 241, 231, 255), "diamond", 0.6, "uncommon"),
        ],
    ),
    (
        "Eyes",
        False,
        20,
        [
            ("Dot", (20, 18, 16, 255), "dots", 1, ""),
            ("Line", (20, 18, 16, 255), "line", 1, ""),
            ("Wide", (214, 255, 63, 255), "wide", 0.45, "rare"),
        ],
    ),
    (
        "Mark",
        False,
        30,
        [
            ("Star", (214, 255, 63, 255), "star", 1, ""),
            ("Ring", (255, 90, 54, 255), "ring", 1, ""),
            ("Dash", (246, 241, 231, 255), "dash", 0.25, "legendary"),
        ],
    ),
]


def build_sample_layers(db: Session, project, user_id: str, replace: bool = False) -> int:
    existing = db.query(TraitCategory).filter_by(project_id=project.id).count()
    if existing and not replace:
        raise ValueError("This project already has layers. Replace them to load the sample set.")
    if replace:
        db.query(TraitRule).filter_by(project_id=project.id).delete()
        db.query(Trait).filter_by(project_id=project.id).delete()
        db.query(TraitCategory).filter_by(project_id=project.id).delete()
        db.flush()
    created = 0
    for name, optional, z_index, traits in SAMPLE_LAYERS:
        category = TraitCategory(project_id=project.id, name=name, z_index=z_index, optional=optional, none_weight=1)
        db.add(category)
        db.flush()
        for trait_name, color, shape, weight, rarity in traits:
            image = _sample_art(shape, project.canvas_width, project.canvas_height, color)
            asset = store_image(
                db,
                project_id=project.id,
                user_id=user_id,
                image=image,
                name=f"{name}-{trait_name}",
                kind="trait",
            )
            db.add(
                Trait(
                    project_id=project.id,
                    category_id=category.id,
                    asset_id=asset.id,
                    name=trait_name,
                    weight=weight,
                    rarity_label=rarity,
                )
            )
            created += 1
    return created


def snapshot_traits(db: Session, project_id: str) -> dict:
    categories = db.query(TraitCategory).filter_by(project_id=project_id).order_by(TraitCategory.z_index).all()
    traits = db.query(Trait).filter_by(project_id=project_id).all()
    rules = db.query(TraitRule).filter_by(project_id=project_id).all()
    trait_by_id = {trait.id: trait for trait in traits}
    payload_categories = []
    for category in categories:
        group = []
        for trait in traits:
            if trait.category_id != category.id:
                continue
            asset = db.get(Asset, trait.asset_id) if trait.asset_id else None
            group.append(
                {
                    "name": trait.name,
                    "weight": trait.weight,
                    "exact_count": trait.exact_count,
                    "always_include": trait.always_include,
                    "rarity_label": trait.rarity_label,
                    "storage_key": asset.storage_key if asset else None,
                    "thumb_key": asset.thumb_key if asset else None,
                    "width": asset.width if asset else None,
                    "height": asset.height if asset else None,
                    "sha256": asset.sha256 if asset else None,
                    "mime": asset.mime if asset else None,
                    "size": asset.size if asset else None,
                }
            )
        payload_categories.append(
            {
                "name": category.name,
                "z_index": category.z_index,
                "optional": category.optional,
                "none_weight": category.none_weight,
                "traits": group,
            }
        )
    payload_rules = []
    for rule in rules:
        left = trait_by_id.get(rule.trait_a_id)
        right = trait_by_id.get(rule.trait_b_id)
        if not left or not right:
            continue
        left_cat = next(cat.name for cat in categories if cat.id == left.category_id)
        right_cat = next(cat.name for cat in categories if cat.id == right.category_id)
        payload_rules.append(
            {"rule_type": rule.rule_type, "a_category": left_cat, "a_name": left.name, "b_category": right_cat, "b_name": right.name}
        )
    return {"categories": payload_categories, "rules": payload_rules}


def apply_trait_template(db: Session, project, user_id: str, payload: dict) -> None:
    existing = db.query(TraitCategory).filter_by(project_id=project.id).count()
    if existing:
        raise ValueError("Apply templates to a project that does not already have layers")
    index: dict[tuple[str, str], Trait] = {}
    for category_data in payload.get("categories", []):
        category = TraitCategory(
            project_id=project.id,
            name=category_data["name"],
            z_index=category_data.get("z_index", 0),
            optional=category_data.get("optional", False),
            none_weight=category_data.get("none_weight", 1),
        )
        db.add(category)
        db.flush()
        for trait_data in category_data.get("traits", []):
            asset_id = None
            if trait_data.get("storage_key"):
                asset = Asset(
                    project_id=project.id,
                    filename=f"{trait_data['name']}.png",
                    original_name=f"{trait_data['name']}.png",
                    mime=trait_data.get("mime") or "image/png",
                    size=trait_data.get("size") or 0,
                    width=trait_data.get("width") or project.canvas_width,
                    height=trait_data.get("height") or project.canvas_height,
                    sha256=trait_data.get("sha256") or "",
                    storage_key=trait_data["storage_key"],
                    thumb_key=trait_data.get("thumb_key"),
                    kind="trait",
                    created_by=user_id,
                )
                db.add(asset)
                db.flush()
                asset_id = asset.id
            trait = Trait(
                project_id=project.id,
                category_id=category.id,
                asset_id=asset_id,
                name=trait_data["name"],
                weight=trait_data.get("weight", 1),
                exact_count=trait_data.get("exact_count"),
                always_include=trait_data.get("always_include", False),
                rarity_label=trait_data.get("rarity_label", ""),
            )
            db.add(trait)
            db.flush()
            index[(category.name, trait.name)] = trait
    for rule in payload.get("rules", []):
        left = index.get((rule["a_category"], rule["a_name"]))
        right = index.get((rule["b_category"], rule["b_name"]))
        if left and right:
            db.add(TraitRule(project_id=project.id, rule_type=rule["rule_type"], trait_a_id=left.id, trait_b_id=right.id))
