"""ZIP export and provenance bundle."""

from __future__ import annotations

import io
import json
import zipfile

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Asset, Collection, ExportRecord, MetadataRecord, NFTAttribute, NFTItem, Project
from app.services.collections import assess_collection, file_bytes_for_item
from app.services.metadata import metadata_to_csv


def collection_rows(db: Session, collection: Collection) -> list[dict]:
    items = db.query(NFTItem).filter_by(collection_id=collection.id).order_by(NFTItem.token_id).all()
    rows = []
    for item in items:
        record = db.query(MetadataRecord).filter_by(item_id=item.id).one_or_none()
        body = dict(record.body if record else {})
        body["token_id"] = item.token_id
        rows.append(body)
    return rows


def provenance(db: Session, collection: Collection, project: Project) -> dict:
    items = db.query(NFTItem).filter_by(collection_id=collection.id).order_by(NFTItem.token_id).all()
    tokens = []
    for item in items:
        attributes = [
            {"trait_type": row.trait_type, "value": row.value}
            for row in db.query(NFTAttribute).filter_by(item_id=item.id).all()
        ]
        image_sha = None
        if item.image_asset_id:
            asset = db.get(Asset, item.image_asset_id)
            image_sha = asset.sha256 if asset else None
        tokens.append(
            {
                "token_id": item.token_id,
                "combination": item.combination_key,
                "seed": item.seed,
                "image_sha256": image_sha,
                "image_dhash": item.image_dhash,
                "attributes": attributes,
                "changes": item.change_log or [],
            }
        )
    return {
        "project": project.name,
        "collection": collection.name,
        "license": project.license,
        "ai_disclosure": project.ai_disclosure,
        "generation_seed": collection.seed,
        "mode": collection.mode,
        "schema": collection.metadata_schema,
        "tokens": tokens,
    }


def build_zip(db: Session, collection: Collection, project: Project, user_id: str | None, force: bool = False) -> tuple[bytes, dict]:
    items = db.query(NFTItem).filter_by(collection_id=collection.id).order_by(NFTItem.token_id).all()
    if not items or any(item.image_asset_id is None for item in items):
        raise HTTPException(status_code=422, detail="Render the collection before exporting")
    report = assess_collection(db, collection, project)
    collection.last_report = report
    if report["blocking"] and not force:
        raise HTTPException(status_code=422, detail={"message": "Fix validation errors or export anyway", "report": report})
    rows = collection_rows(db, collection)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for item, row in zip(items, rows):
            bundle.writestr(f"images/{item.token_id}.png", file_bytes_for_item(db, item))
            public_row = {key: value for key, value in row.items() if key != "token_id"}
            bundle.writestr(f"metadata/{item.token_id}.json", json.dumps(public_row, indent=2))
        bundle.writestr("metadata.csv", metadata_to_csv(rows))
        bundle.writestr("report.json", json.dumps(report, indent=2))
        bundle.writestr("provenance.json", json.dumps(provenance(db, collection, project), indent=2))
    payload = archive.getvalue()
    from app.storage import write_bytes

    key, _digest = write_bytes(payload, ".zip")
    db.add(
        ExportRecord(
            project_id=project.id,
            collection_id=collection.id,
            kind="zip",
            status="ready",
            storage_key=key,
            report=report,
        )
    )
    db.commit()
    return payload, report
