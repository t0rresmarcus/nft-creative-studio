"""Delete a project and the database rows that belong to it."""

from sqlalchemy.orm import Session

from app.models import (
    Approval,
    Asset,
    Collection,
    Comment,
    EditHistory,
    ExportRecord,
    Job,
    MetadataRecord,
    NFTAttribute,
    NFTItem,
    Project,
    ProjectMember,
    Trait,
    TraitCategory,
    TraitRule,
    Workflow,
)


def delete_project(db: Session, project: Project) -> None:
    collection_ids = [row[0] for row in db.query(Collection.id).filter_by(project_id=project.id).all()]
    if collection_ids:
        item_ids = [row[0] for row in db.query(NFTItem.id).filter(NFTItem.collection_id.in_(collection_ids)).all()]
        if item_ids:
            db.query(Approval).filter(Approval.item_id.in_(item_ids)).delete(synchronize_session=False)
            db.query(NFTAttribute).filter(NFTAttribute.item_id.in_(item_ids)).delete(synchronize_session=False)
            db.query(MetadataRecord).filter(MetadataRecord.item_id.in_(item_ids)).delete(synchronize_session=False)
            db.query(NFTItem).filter(NFTItem.id.in_(item_ids)).delete(synchronize_session=False)
        db.query(Collection).filter(Collection.id.in_(collection_ids)).delete(synchronize_session=False)
    asset_ids = [row[0] for row in db.query(Asset.id).filter_by(project_id=project.id).all()]
    if asset_ids:
        db.query(EditHistory).filter(EditHistory.asset_id.in_(asset_ids)).delete(synchronize_session=False)
    db.query(TraitRule).filter_by(project_id=project.id).delete(synchronize_session=False)
    db.query(Trait).filter_by(project_id=project.id).delete(synchronize_session=False)
    db.query(TraitCategory).filter_by(project_id=project.id).delete(synchronize_session=False)
    db.query(ExportRecord).filter_by(project_id=project.id).delete(synchronize_session=False)
    db.query(Job).filter_by(project_id=project.id).delete(synchronize_session=False)
    db.query(Comment).filter_by(project_id=project.id).delete(synchronize_session=False)
    db.query(Workflow).filter_by(project_id=project.id).delete(synchronize_session=False)
    db.query(ProjectMember).filter_by(project_id=project.id).delete(synchronize_session=False)
    db.query(Asset).filter_by(project_id=project.id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
