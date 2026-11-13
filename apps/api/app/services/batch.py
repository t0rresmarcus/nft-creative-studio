"""Batch workflow runner."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.models import Asset, Workflow
from app.security import utcnow
from app.services.imaging import condition_matches, run_operations
from app.services.library import safe_stem, store_image
from app.services.metadata import SafeDict
from app.storage import image_to_format, read_bytes, open_image


CATALOG = [
    {"type": "crop", "label": "Crop", "params": [
        {"name": "x", "kind": "number", "default": 0},
        {"name": "y", "kind": "number", "default": 0},
        {"name": "width", "kind": "number", "default": 1024},
        {"name": "height", "kind": "number", "default": 1024},
    ]},
    {"type": "resize", "label": "Resize", "params": [
        {"name": "width", "kind": "number", "default": 1024},
        {"name": "height", "kind": "number", "default": 1024},
        {"name": "fit", "kind": "select", "options": ["exact", "contain", "cover"], "default": "exact"},
    ], "randomizable": ["width", "height"]},
    {"type": "rotate", "label": "Rotate", "params": [{"name": "degrees", "kind": "number", "default": 0}], "randomizable": ["degrees"]},
    {"type": "flip", "label": "Flip", "params": [{"name": "axis", "kind": "select", "options": ["horizontal", "vertical"], "default": "horizontal"}]},
    {"type": "brightness", "label": "Brightness", "params": [{"name": "factor", "kind": "number", "default": 1}], "randomizable": ["factor"]},
    {"type": "contrast", "label": "Contrast", "params": [{"name": "factor", "kind": "number", "default": 1}], "randomizable": ["factor"]},
    {"type": "saturation", "label": "Saturation", "params": [{"name": "factor", "kind": "number", "default": 1}], "randomizable": ["factor"]},
    {"type": "hue", "label": "Hue shift", "params": [{"name": "degrees", "kind": "number", "default": 0}], "randomizable": ["degrees"]},
    {"type": "sharpen", "label": "Sharpen", "params": []},
    {"type": "remove_background", "label": "Remove background", "params": [
        {"name": "tolerance", "kind": "number", "default": 32},
        {"name": "mode", "kind": "select", "options": ["corner", "ai"], "default": "corner"},
    ]},
    {"type": "replace_background", "label": "Replace background", "params": [
        {"name": "color", "kind": "color", "default": "#111111"},
        {"name": "tolerance", "kind": "number", "default": 32},
        {"name": "mode", "kind": "select", "options": ["corner", "ai"], "default": "corner"},
    ]},
    {"type": "inpaint", "label": "Remove rectangle", "params": [
        {"name": "x", "kind": "number", "default": 0},
        {"name": "y", "kind": "number", "default": 0},
        {"name": "width", "kind": "number", "default": 64},
        {"name": "height", "kind": "number", "default": 64},
    ]},
    {"type": "format", "label": "Convert format", "params": [
        {"name": "format", "kind": "select", "options": ["png", "jpeg", "webp"], "default": "png"},
        {"name": "background", "kind": "color", "default": "#111111"},
    ]},
    {"type": "rename", "label": "Rename", "params": [
        {"name": "pattern", "kind": "string", "default": "{project}-{index}"},
    ]},
]


def render_name(pattern: str, *, index: int, name: str, project: str) -> str:
    return pattern.format_map(SafeDict(index=f"{index:04d}", name=safe_stem(name), project=safe_stem(project), n=index))


def _output_format(operations: list[dict]) -> tuple[str, str]:
    fmt = "png"
    background = "#111111"
    for operation in operations:
        if operation.get("type") == "format":
            fmt = (operation.get("params") or {}).get("format", fmt)
            background = (operation.get("params") or {}).get("background", background)
    return fmt, background


def _rename(operations: list[dict], index: int, name: str, project: str) -> str:
    renamed = safe_stem(name)
    for operation in operations:
        if operation.get("type") == "rename":
            pattern = (operation.get("params") or {}).get("pattern") or "{project}-{index}"
            renamed = render_name(pattern, index=index, name=name, project=project)
    return renamed


def _prepare(asset: Asset, operations: list[dict], seed: int, project_name: str, index: int):
    source = open_image(read_bytes(asset.storage_key))
    file_seed = seed + (int(asset.sha256[:8], 16) % 1_000_000)
    # Skip steps whose condition fails. run_operations checks the image as it changes.
    active = []
    probe = source
    for operation in operations:
        if operation.get("type") in {"format", "rename"}:
            active.append(operation)
            continue
        if condition_matches(operation, probe, asset.original_name):
            active.append(operation)
            probe, _note = run_operations(probe, [operation], file_seed, asset.original_name)
    image, notes = run_operations(source, [step for step in active if step.get("type") not in {"format", "rename"}], file_seed, asset.original_name)
    fmt, background = _output_format(operations)
    blob, suffix = image_to_format(image, fmt, background)
    from io import BytesIO
    from PIL import Image

    saved = Image.open(BytesIO(blob))
    saved.load()
    name = _rename(operations, index, asset.original_name, project_name) + suffix
    return saved, name, notes


def run_batch(db: Session, workflow: Workflow, asset_ids: list[str], seed: int, dry_run: bool, project_name: str, user_id: str | None, job=None) -> dict:
    assets = db.query(Asset).filter(Asset.id.in_(asset_ids), Asset.project_id == workflow.project_id).all()
    order = {asset_id: index for index, asset_id in enumerate(asset_ids)}
    assets.sort(key=lambda asset: order.get(asset.id, 0))
    if dry_run:
        assets = assets[:8]
    if not assets:
        raise ValueError("Choose at least one image")
    outputs = []
    workers = min(4, len(assets))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        prepared = list(
            pool.map(
                lambda pair: _prepare(pair[1], workflow.operations or [], seed, project_name, pair[0] + 1),
                list(enumerate(assets)),
            )
        )
    for asset, (image, name, notes) in zip(assets, prepared):
        stored = store_image(
            db,
            project_id=workflow.project_id,
            user_id=user_id,
            image=image.convert("RGBA"),
            name=name,
            kind="preview" if dry_run else "render",
            parent_asset_id=asset.id,
        )
        stored.original_name = name
        outputs.append({"source_id": asset.id, "asset_id": stored.id, "name": name, "notes": notes})
        if job is not None:
            job.progress = len(outputs) / len(assets)
            job.updated_at = utcnow()
            db.commit()
    db.commit()
    return {"outputs": outputs, "dry_run": dry_run, "workflow_version": workflow.version, "seed": seed}
