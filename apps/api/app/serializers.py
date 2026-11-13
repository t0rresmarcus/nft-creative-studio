from app.models import Asset, Collection, Comment, Job, NFTItem, Project, Trait, TraitCategory, TraitRule, User, Workflow
from app.security import sign_asset_url


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "plan": user.plan,
        "credits": user.credits,
        "ipfs_configured": bool(user.ipfs_secret),
        "created_at": user.created_at.isoformat(),
    }


def asset_out(asset: Asset) -> dict:
    return {
        "id": asset.id,
        "project_id": asset.project_id,
        "parent_asset_id": asset.parent_asset_id,
        "filename": asset.filename,
        "original_name": asset.original_name,
        "mime": asset.mime,
        "size": asset.size,
        "width": asset.width,
        "height": asset.height,
        "sha256": asset.sha256,
        "kind": asset.kind,
        "url": sign_asset_url(asset.id, "full"),
        "thumb_url": sign_asset_url(asset.id, "thumb") if asset.thumb_key else sign_asset_url(asset.id, "full"),
        "created_at": asset.created_at.isoformat(),
    }


def trait_out(trait: Trait, asset: Asset | None) -> dict:
    return {
        "id": trait.id,
        "category_id": trait.category_id,
        "name": trait.name,
        "weight": trait.weight,
        "exact_count": trait.exact_count,
        "always_include": trait.always_include,
        "rarity_label": trait.rarity_label,
        "asset_id": trait.asset_id,
        "url": sign_asset_url(asset.id, "thumb") if asset else None,
    }


def category_out(category: TraitCategory, traits: list[dict]) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "z_index": category.z_index,
        "optional": category.optional,
        "none_weight": category.none_weight,
        "traits": traits,
    }


def rule_out(rule: TraitRule) -> dict:
    return {"id": rule.id, "rule_type": rule.rule_type, "trait_a_id": rule.trait_a_id, "trait_b_id": rule.trait_b_id}


def project_out(project: Project, role: str, asset_count: int = 0, collection_count: int = 0) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "project_type": project.project_type,
        "canvas_width": project.canvas_width,
        "canvas_height": project.canvas_height,
        "license": project.license,
        "ai_disclosure": project.ai_disclosure,
        "role": role,
        "asset_count": asset_count,
        "collection_count": collection_count,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def collection_out(collection: Collection) -> dict:
    return {
        "id": collection.id,
        "project_id": collection.project_id,
        "name": collection.name,
        "supply": collection.supply,
        "seed": collection.seed,
        "mode": collection.mode,
        "description_template": collection.description_template,
        "image_base_uri": collection.image_base_uri,
        "external_url": collection.external_url,
        "symbol": collection.symbol,
        "metadata_schema": collection.metadata_schema,
        "marketplace_profile": collection.marketplace_profile,
        "status": collection.status,
        "created_at": collection.created_at.isoformat(),
    }


def item_out(item: NFTItem, attributes: list[dict], metadata: dict | None) -> dict:
    return {
        "id": item.id,
        "token_id": item.token_id,
        "combination_key": item.combination_key,
        "seed": item.seed,
        "image_url": sign_asset_url(item.image_asset_id, "full") if item.image_asset_id else None,
        "thumb_url": sign_asset_url(item.image_asset_id, "thumb") if item.image_asset_id else None,
        "image_dhash": item.image_dhash,
        "attributes": attributes,
        "metadata": metadata,
        "changes": item.change_log or [],
    }


def job_out(job: Job) -> dict:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "error": job.error,
        "result": job.result,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def workflow_out(workflow: Workflow) -> dict:
    return {
        "id": workflow.id,
        "project_id": workflow.project_id,
        "name": workflow.name,
        "description": workflow.description,
        "operations": workflow.operations or [],
        "version": workflow.version,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
    }


def comment_out(comment: Comment, author: User | None) -> dict:
    return {
        "id": comment.id,
        "project_id": comment.project_id,
        "item_id": comment.item_id,
        "body": comment.body,
        "author": author.name if author else "Unknown",
        "created_at": comment.created_at.isoformat(),
    }
