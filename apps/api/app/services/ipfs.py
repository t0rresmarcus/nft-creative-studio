"""Optional Pinata pinning and local content-addressed verification."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Collection, ExportRecord, MetadataRecord, NFTItem, Project, User
from app.security import decrypt_secret, utcnow
from app.services.collections import assess_collection, file_bytes_for_item, refresh_metadata
from app.services.metadata import validate_metadata
from app.storage import read_bytes


def find_blob(digest: str) -> Path | None:
    if len(digest) < 8 or any(character not in "0123456789abcdef" for character in digest):
        return None
    folder = settings.storage_path / digest[:2]
    if not folder.exists():
        return None
    matches = list(folder.glob(digest + ".*"))
    return matches[0] if matches else None


def _pinata_pin(jwt: str, data: bytes, name: str, content_type: str) -> str:
    response = httpx.post(
        "https://api.pinata.cloud/pinning/pinFileToIPFS",
        headers={"Authorization": f"Bearer {jwt}"},
        files={"file": (name, data, content_type)},
        data={"pinataMetadata": json.dumps({"name": name})},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["IpfsHash"]


def _verify_pinata(cid: str) -> bool:
    try:
        response = httpx.get(f"https://gateway.pinata.cloud/ipfs/{cid}", timeout=45)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def pin_collection(db: Session, collection: Collection, project: Project, user: User, job=None) -> dict:
    items = db.query(NFTItem).filter_by(collection_id=collection.id).order_by(NFTItem.token_id).all()
    if not items or any(item.image_asset_id is None for item in items):
        raise ValueError("Render the collection before uploading")
    previous = (
        db.query(ExportRecord)
        .filter_by(collection_id=collection.id, kind="ipfs")
        .order_by(ExportRecord.created_at.desc())
        .first()
    )
    done = dict((previous.cids if previous and previous.cids else {}) or {})
    jwt = decrypt_secret(user.ipfs_secret) if user.ipfs_secret else ""
    mode = "pinata" if jwt else "local"
    mapping: dict[str, dict] = dict(done)
    total = len(items)
    for index, item in enumerate(items):
        key = str(item.token_id)
        current = dict(mapping.get(key) or {})
        image_bytes = file_bytes_for_item(db, item)
        if not current.get("image"):
            if jwt:
                cid = _pinata_pin(jwt, image_bytes, f"{item.token_id}.png", "image/png")
                verified = _verify_pinata(cid)
                if not verified:
                    raise RuntimeError(f"Pinata accepted token {item.token_id} but the gateway did not return it")
                current["image"] = cid
                current["image_uri"] = f"ipfs://{cid}"
            else:
                from hashlib import sha256

                digest = sha256(image_bytes).hexdigest()
                current["image"] = digest
                current["image_uri"] = f"{settings.public_base_url.rstrip('/')}/api/content/{digest}"
                current["verified"] = find_blob(digest) is not None
        record = db.query(MetadataRecord).filter_by(item_id=item.id).one()
        body = dict(record.body)
        body["image"] = current["image_uri"]
        if collection.metadata_schema == "metaplex":
            body["properties"] = {"files": [{"uri": current["image_uri"], "type": "image/png"}], "category": "image"}
        errors = validate_metadata(body, collection.metadata_schema)
        record.body = body
        record.errors = errors
        record.valid = not errors
        record.updated_at = utcnow()
        if not current.get("metadata"):
            encoded = json.dumps(body, indent=2).encode()
            if jwt:
                meta_cid = _pinata_pin(jwt, encoded, f"{item.token_id}.json", "application/json")
                if not _verify_pinata(meta_cid):
                    raise RuntimeError(f"Metadata for token {item.token_id} could not be fetched back from the gateway")
                current["metadata"] = meta_cid
                current["metadata_uri"] = f"ipfs://{meta_cid}"
            else:
                from app.storage import write_bytes

                _key, digest = write_bytes(encoded, ".json")
                current["metadata"] = digest
                current["metadata_uri"] = f"{settings.public_base_url.rstrip('/')}/api/content/{digest}"
        current["verified"] = True
        mapping[key] = current
        if job is not None:
            job.progress = (index + 1) / total
            job.result = {"mode": mode, "cids": mapping}
            job.updated_at = utcnow()
            db.commit()
    export = ExportRecord(
        project_id=project.id,
        collection_id=collection.id,
        kind="ipfs",
        status="ready",
        cids=mapping,
        report={"mode": mode, "count": len(mapping)},
    )
    db.add(export)
    report = assess_collection(db, collection, project)
    collection.last_report = report
    db.commit()
    return {"mode": mode, "cids": mapping, "report": report}
