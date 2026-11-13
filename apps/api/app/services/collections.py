"""Collection planning, rendering, regeneration, and QA reports."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    Asset,
    Collection,
    MetadataRecord,
    NFTAttribute,
    NFTItem,
    Project,
    Trait,
    TraitCategory,
    TraitRule,
)
from app.security import utcnow
from app.services.generator import CategoryIn, GeneratedToken, RuleIn, TraitIn, combination_key, generate, pick_one
from app.services.generator import GenerationError
from app.services.imaging import composite, dhash, hamming, resize_image
from app.services.library import load_asset_image, store_image
from app.services.metadata import PROFILES, build_metadata, validate_metadata
from app.storage import read_bytes


def clear_items(db: Session, collection_id: str) -> None:
    item_ids = [row[0] for row in db.query(NFTItem.id).filter_by(collection_id=collection_id).all()]
    if not item_ids:
        return
    from app.models import Approval

    db.query(Approval).filter(Approval.item_id.in_(item_ids)).delete(synchronize_session=False)
    db.query(NFTAttribute).filter(NFTAttribute.item_id.in_(item_ids)).delete(synchronize_session=False)
    db.query(MetadataRecord).filter(MetadataRecord.item_id.in_(item_ids)).delete(synchronize_session=False)
    db.query(NFTItem).filter(NFTItem.id.in_(item_ids)).delete(synchronize_session=False)
    db.flush()


def load_graph(db: Session, project_id: str):
    categories = db.query(TraitCategory).filter_by(project_id=project_id).all()
    traits = db.query(Trait).filter_by(project_id=project_id).all()
    rules = db.query(TraitRule).filter_by(project_id=project_id).all()
    category_in = [
        CategoryIn(
            id=category.id,
            name=category.name,
            z_index=category.z_index,
            optional=category.optional,
            none_weight=category.none_weight,
        )
        for category in categories
    ]
    trait_in = [
        TraitIn(
            id=trait.id,
            category_id=trait.category_id,
            name=trait.name,
            weight=trait.weight,
            exact_count=trait.exact_count,
            always_include=trait.always_include,
        )
        for trait in traits
    ]
    rule_in = [RuleIn(rule.rule_type, rule.trait_a_id, rule.trait_b_id) for rule in rules]
    return category_in, trait_in, rule_in, {trait.id: trait for trait in traits}, {category.id: category for category in categories}


def _ordered_attributes(selection: dict, categories: dict, traits: dict) -> list[dict]:
    ordered = sorted(categories.values(), key=lambda category: (category.z_index, category.name))
    attributes = []
    for category in ordered:
        trait_id = selection.get(category.id)
        if not trait_id:
            continue
        trait = traits[trait_id]
        attributes.append({"trait_type": category.name, "value": trait.name, "trait_id": trait.id})
    return attributes


def _write_metadata(db: Session, collection: Collection, project: Project, item: NFTItem, attributes: list[dict]) -> MetadataRecord:
    body = build_metadata(
        collection_name=collection.name,
        symbol=collection.symbol,
        description_template=collection.description_template,
        image_base_uri=collection.image_base_uri,
        external_url=collection.external_url,
        schema=collection.metadata_schema,
        token_id=item.token_id,
        attributes=[{"trait_type": row["trait_type"], "value": row["value"]} for row in attributes],
        license_name=project.license,
        ai_disclosure=project.ai_disclosure,
    )
    errors = validate_metadata(body, collection.metadata_schema)
    record = db.query(MetadataRecord).filter_by(item_id=item.id).one_or_none()
    if record is None:
        record = MetadataRecord(item_id=item.id)
        db.add(record)
    record.body = body
    record.valid = not errors
    record.errors = errors
    record.schema_name = collection.metadata_schema
    record.updated_at = utcnow()
    return record


def _persist_token(db: Session, collection: Collection, project: Project, token: GeneratedToken, traits: dict, categories: dict) -> NFTItem:
    item = NFTItem(
        collection_id=collection.id,
        token_id=token.token_id,
        combination_key=token.combination_key,
        seed=collection.seed,
        change_log=[],
    )
    db.add(item)
    db.flush()
    attributes = _ordered_attributes(token.selection, categories, traits)
    for attribute in attributes:
        db.add(
            NFTAttribute(
                item_id=item.id,
                trait_id=attribute["trait_id"],
                trait_type=attribute["trait_type"],
                value=attribute["value"],
            )
        )
    _write_metadata(db, collection, project, item, attributes)
    return item


def plan_collection(db: Session, collection: Collection, project: Project) -> dict:
    categories, traits, rules, trait_map, category_map = load_graph(db, project.id)
    result = generate(categories, traits, rules, collection.supply, collection.seed, collection.mode)
    clear_items(db, collection.id)
    for token in result.tokens:
        _persist_token(db, collection, project, token, trait_map, category_map)
    collection.status = "planned"
    collection.updated_at = utcnow()
    report = {
        "status": "planned",
        "blocking": [],
        "warnings": [{"code": "not_rendered", "message": warning} for warning in result.warnings],
        "distribution": result.stats["distribution"],
        "supply": collection.supply,
        "unique": result.stats["unique"],
        "mode": collection.mode,
        "seed": collection.seed,
        "valid_space": result.stats["valid_space"],
        "rendered": 0,
    }
    report["warnings"].append(
        {
            "code": "not_rendered",
            "message": "Combinations are planned. Render the collection to create images and run image duplicate checks.",
        }
    )
    collection.last_report = report
    db.commit()
    return report


def render_selection_image(db: Session, project: Project, selection: dict[str, str | None]):
    _categories, _traits, _rules, trait_map, category_map = load_graph(db, project.id)
    warnings = []
    layers = []
    ordered = sorted(category_map.values(), key=lambda category: (category.z_index, category.id))
    for category in ordered:
        trait_id = selection.get(category.id)
        if not trait_id:
            continue
        trait = trait_map[trait_id]
        if not trait.asset_id:
            raise GenerationError(f'Trait "{trait.name}" has no artwork')
        asset = db.get(Asset, trait.asset_id)
        if asset is None:
            raise GenerationError(f'Artwork for "{trait.name}" is missing')
        image = load_asset_image(asset)
        if image.size != (project.canvas_width, project.canvas_height):
            warnings.append(f'{category.name} / {trait.name} is {image.width}×{image.height} and was resized to the canvas')
            image = resize_image(image, project.canvas_width, project.canvas_height, "exact")
        layers.append({"image": image, "x": 0, "y": 0, "scale": 1, "opacity": 1})
    if not layers:
        raise GenerationError("This combination has no visible traits")
    return composite((project.canvas_width, project.canvas_height), layers), warnings


def _item_selection(db: Session, item: NFTItem, category_map: dict) -> dict[str, str | None]:
    attributes = db.query(NFTAttribute).filter_by(item_id=item.id).all()
    by_name = {category.name: category.id for category in category_map.values()}
    selection = {category.id: None for category in category_map.values()}
    for attribute in attributes:
        category_id = by_name.get(attribute.trait_type)
        if category_id:
            selection[category_id] = attribute.trait_id
    return selection


def render_collection(db: Session, collection: Collection, project: Project, job=None) -> dict:
    items = db.query(NFTItem).filter_by(collection_id=collection.id).order_by(NFTItem.token_id).all()
    if not items:
        plan_collection(db, collection, project)
        items = db.query(NFTItem).filter_by(collection_id=collection.id).order_by(NFTItem.token_id).all()
    _categories, _traits, _rules, _trait_map, category_map = load_graph(db, project.id)
    dimension_notes: list[str] = []
    collection.status = "rendering"
    db.commit()
    for index, item in enumerate(items):
        selection = _item_selection(db, item, category_map)
        image, notes = render_selection_image(db, project, selection)
        dimension_notes.extend(notes)
        asset = store_image(
            db,
            project_id=project.id,
            user_id=None,
            image=image,
            name=str(item.token_id),
            kind="render",
        )
        item.image_asset_id = asset.id
        item.image_dhash = dhash(image)
        if job is not None:
            job.progress = (index + 1) / len(items)
            job.updated_at = utcnow()
        db.commit()
    report = assess_collection(db, collection, project, extra_warnings=dimension_notes)
    collection.status = "ready" if not report["blocking"] else "ready"
    collection.last_report = report
    collection.updated_at = utcnow()
    db.commit()
    return report


def regenerate_item(db: Session, collection: Collection, project: Project, item: NFTItem) -> NFTItem:
    categories, traits, rules, trait_map, category_map = load_graph(db, project.id)
    others = db.query(NFTItem).filter(NFTItem.collection_id == collection.id, NFTItem.id != item.id).all()
    blocked = {other.combination_key for other in others}
    blocked.add(item.combination_key)
    selection = pick_one(categories, traits, rules, item.seed + len(item.change_log or []) + 7, blocked)
    key = combination_key(selection)
    item.change_log = list(item.change_log or []) + [
        {"at": utcnow().isoformat(), "previous": item.combination_key, "next": key}
    ]
    item.combination_key = key
    item.seed = item.seed + 1
    db.query(NFTAttribute).filter_by(item_id=item.id).delete()
    attributes = _ordered_attributes(selection, category_map, trait_map)
    for attribute in attributes:
        db.add(
            NFTAttribute(
                item_id=item.id,
                trait_id=attribute["trait_id"],
                trait_type=attribute["trait_type"],
                value=attribute["value"],
            )
        )
    image, _notes = render_selection_image(db, project, selection)
    asset = store_image(db, project_id=project.id, user_id=None, image=image, name=str(item.token_id), kind="render")
    item.image_asset_id = asset.id
    item.image_dhash = dhash(image)
    _write_metadata(db, collection, project, item, attributes)
    report = assess_collection(db, collection, project)
    collection.last_report = report
    collection.updated_at = utcnow()
    db.commit()
    db.refresh(item)
    return item


def assess_collection(db: Session, collection: Collection, project: Project, extra_warnings: list[str] | None = None) -> dict:
    items = db.query(NFTItem).filter_by(collection_id=collection.id).order_by(NFTItem.token_id).all()
    profile = PROFILES.get(collection.marketplace_profile, PROFILES["generic"])
    blocking = []
    warnings = []
    keys = [item.combination_key for item in items]
    if len(keys) != len(set(keys)):
        blocking.append({"code": "duplicate_combination", "message": "Two tokens share the same trait combination"})
    metadata_errors = []
    rendered = 0
    near = []
    rendered_items = []
    for item in items:
        if not item.image_dhash or not item.image_asset_id:
            continue
        asset = db.get(Asset, item.image_asset_id)
        rendered_items.append((item, asset.sha256 if asset else ""))
    pools = [rendered_items]
    if len(rendered_items) > 1200:
        grouped: dict[str, list] = {}
        for entry in rendered_items:
            grouped.setdefault(entry[0].image_dhash[:4], []).append(entry)
        pools = list(grouped.values())
    for pool in pools:
        for left_index in range(len(pool)):
            for right_index in range(left_index + 1, len(pool)):
                left_item, left_sha = pool[left_index]
                right_item, right_sha = pool[right_index]
                if left_sha and left_sha == right_sha:
                    blocking.append(
                        {
                            "code": "identical_image",
                            "message": f"Tokens {left_item.token_id} and {right_item.token_id} rendered identical images",
                            "token_id": left_item.token_id,
                        }
                    )
                    continue
                distance = hamming(left_item.image_dhash, right_item.image_dhash)
                if distance <= 5:
                    near.append({"token_a": left_item.token_id, "token_b": right_item.token_id, "distance": distance})
    if near:
        warnings.append({"code": "near_duplicate", "message": f"{len(near)} token pairs look very similar"})
    for item in items:
        record = db.query(MetadataRecord).filter_by(item_id=item.id).one_or_none()
        if record is None:
            metadata_errors.append({"token_id": item.token_id, "errors": ["missing metadata"]})
            blocking.append({"code": "metadata", "message": f"Token {item.token_id} has no metadata", "token_id": item.token_id})
        elif record.errors:
            metadata_errors.append({"token_id": item.token_id, "errors": record.errors})
            blocking.append(
                {
                    "code": "metadata",
                    "message": f"Token {item.token_id}: {', '.join(record.errors)}",
                    "token_id": item.token_id,
                }
            )
        else:
            image_value = record.body.get("image", "")
            if not image_value.startswith(("ipfs://", "https://", "http://", "ar://")):
                warnings.append(
                    {
                        "code": "relative_uri",
                        "message": f"Token {item.token_id} uses a relative image URI. Set an IPFS base URI before minting.",
                        "token_id": item.token_id,
                    }
                )
        if item.image_asset_id:
            rendered += 1
            asset = db.get(Asset, item.image_asset_id)
            if asset and asset.size > profile["max_bytes"]:
                blocking.append(
                    {
                        "code": "file_size",
                        "message": f"Token {item.token_id} is {asset.size} bytes, over the {profile['label']} limit",
                        "token_id": item.token_id,
                    }
                )
            if asset and (asset.width != project.canvas_width or asset.height != project.canvas_height):
                warnings.append(
                    {
                        "code": "dimensions",
                        "message": f"Token {item.token_id} is {asset.width}×{asset.height}",
                        "token_id": item.token_id,
                    }
                )
        else:
            blocking.append({"code": "not_rendered", "message": f"Token {item.token_id} has not been rendered", "token_id": item.token_id})
    for note in extra_warnings or []:
        warnings.append({"code": "resized_trait", "message": note})
    # Collapse repeated relative-uri warnings into one so the report stays readable.
    relative = [warning for warning in warnings if warning["code"] == "relative_uri"]
    other_warnings = [warning for warning in warnings if warning["code"] != "relative_uri"]
    if relative:
        other_warnings.append(
            {
                "code": "relative_uri",
                "message": f"{len(relative)} tokens use relative image URIs. Set an IPFS or HTTPS base URI before minting.",
            }
        )
    distribution = (collection.last_report or {}).get("distribution", [])
    report = {
        "status": "fail" if blocking else "pass",
        "blocking": blocking,
        "warnings": other_warnings,
        "near_duplicates": near,
        "metadata_errors": metadata_errors,
        "distribution": distribution,
        "profile": profile,
        "supply": collection.supply,
        "rendered": rendered,
        "schema": collection.metadata_schema,
    }
    return report


def refresh_metadata(db: Session, collection: Collection, project: Project) -> int:
    _categories, _traits, _rules, _trait_map, _category_map = load_graph(db, project.id)
    items = db.query(NFTItem).filter_by(collection_id=collection.id).all()
    for item in items:
        attributes = [
            {"trait_type": row.trait_type, "value": row.value}
            for row in db.query(NFTAttribute).filter_by(item_id=item.id).all()
        ]
        _write_metadata(db, collection, project, item, attributes)
    db.commit()
    return len(items)


def file_bytes_for_item(db: Session, item: NFTItem) -> bytes:
    if not item.image_asset_id:
        raise GenerationError(f"Token {item.token_id} has not been rendered")
    asset = db.get(Asset, item.image_asset_id)
    if asset is None:
        raise GenerationError(f"Token {item.token_id} image is missing")
    return read_bytes(asset.storage_key)
