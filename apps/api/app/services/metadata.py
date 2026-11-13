"""ERC-721 and Metaplex metadata builders and validators."""

from __future__ import annotations

import csv
import io

PROFILES = {
    "opensea": {
        "id": "opensea",
        "label": "OpenSea",
        "max_bytes": 100 * 1024 * 1024,
        "schemas": ["erc721"],
        "notes": "ERC-721 JSON. Use an ipfs:// or https:// image URI before minting.",
    },
    "zora": {
        "id": "zora",
        "label": "Zora",
        "max_bytes": 100 * 1024 * 1024,
        "schemas": ["erc721"],
        "notes": "ERC-721 JSON for Zora drops.",
    },
    "metaplex": {
        "id": "metaplex",
        "label": "Solana Metaplex",
        "max_bytes": 100 * 1024 * 1024,
        "schemas": ["metaplex"],
        "notes": "Metaplex token metadata with properties.files.",
    },
    "generic": {
        "id": "generic",
        "label": "Generic",
        "max_bytes": 200 * 1024 * 1024,
        "schemas": ["erc721", "metaplex"],
        "notes": "Permissive size limit for either schema.",
    },
}


class SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_template(template: str, values: dict) -> str:
    try:
        return template.format_map(SafeDict(values))
    except (ValueError, IndexError):
        return template


def image_uri(base_uri: str, token_id: int) -> str:
    if base_uri:
        return base_uri.replace("{token_id}", str(token_id))
    return f"{token_id}.png"


def build_metadata(
    *,
    collection_name: str,
    symbol: str,
    description_template: str,
    image_base_uri: str,
    external_url: str,
    schema: str,
    token_id: int,
    attributes: list[dict],
    license_name: str,
    ai_disclosure: str,
) -> dict:
    trait_list = ", ".join(f"{item['trait_type']}: {item['value']}" for item in attributes)
    values = {
        "token_id": token_id,
        "collection": collection_name,
        "trait_list": trait_list,
        "symbol": symbol,
    }
    description = render_template(description_template or "{collection} #{token_id} — {trait_list}", values)
    body: dict = {
        "name": f"{collection_name} #{token_id}",
        "description": description,
        "image": image_uri(image_base_uri, token_id),
        "attributes": [{"trait_type": item["trait_type"], "value": item["value"]} for item in attributes],
    }
    if external_url:
        body["external_url"] = external_url.replace("{token_id}", str(token_id))
    if license_name:
        body["license"] = license_name
    if ai_disclosure:
        body["ai_disclosure"] = ai_disclosure
    if schema == "metaplex":
        body["symbol"] = symbol or collection_name[:10]
        body["seller_fee_basis_points"] = 0
        body["properties"] = {
            "files": [{"uri": body["image"], "type": "image/png"}],
            "category": "image",
        }
    return body


def validate_metadata(body: dict, schema: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(body.get("name"), str) or not body["name"].strip():
        errors.append("name is required")
    if not isinstance(body.get("description"), str):
        errors.append("description is required")
    if not isinstance(body.get("image"), str) or not body["image"].strip():
        errors.append("image is required")
    attributes = body.get("attributes")
    if not isinstance(attributes, list):
        errors.append("attributes must be a list")
    else:
        for index, attribute in enumerate(attributes):
            if not isinstance(attribute, dict) or "trait_type" not in attribute or "value" not in attribute:
                errors.append(f"attribute {index + 1} needs trait_type and value")
    if schema == "metaplex":
        properties = body.get("properties")
        if not isinstance(properties, dict) or not properties.get("files"):
            errors.append("metaplex metadata needs properties.files")
        if not body.get("symbol"):
            errors.append("metaplex metadata needs a symbol")
    if schema not in {"erc721", "metaplex"}:
        errors.append("schema must be erc721 or metaplex")
    return errors


def metadata_to_csv(rows: list[dict]) -> str:
    trait_types: list[str] = []
    for row in rows:
        for attribute in row.get("attributes", []):
            if attribute["trait_type"] not in trait_types:
                trait_types.append(attribute["trait_type"])
    fieldnames = ["token_id", "name", "description", "image", *trait_types]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        flat = {
            "token_id": row["token_id"],
            "name": row["name"],
            "description": row["description"],
            "image": row["image"],
        }
        for attribute in row.get("attributes", []):
            flat[attribute["trait_type"]] = attribute["value"]
        writer.writerow(flat)
    return buffer.getvalue()
