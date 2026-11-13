from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, plan_limits, require_project
from app.models import Asset, Job, User, Workflow, WorkflowTemplate
from app.schemas import RunIn, TemplateIn, WorkflowIn
from app.security import utcnow
from app.serializers import job_out, workflow_out
from app.services.batch import CATALOG
from app.services.jobs import create_job, enqueue

router = APIRouter(prefix="/api")


@router.get("/operation-catalog")
def catalog():
    return CATALOG


@router.get("/projects/{project_id}/workflows")
def list_workflows(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id)
    rows = db.query(Workflow).filter_by(project_id=project.id).order_by(Workflow.updated_at.desc()).all()
    return [workflow_out(row) for row in rows]


@router.post("/projects/{project_id}/workflows")
def create_workflow(project_id: str, body: WorkflowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    if not plan_limits(user)["automation"]:
        raise HTTPException(status_code=402, detail="Automation is not included in this plan")
    workflow = Workflow(project_id=project.id, name=body.name.strip(), description=body.description.strip(), operations=body.operations)
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow_out(workflow)


@router.patch("/workflows/{workflow_id}")
def update_workflow(workflow_id: str, body: WorkflowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    require_project(db, user, workflow.project_id, "editor")
    workflow.name = body.name.strip()
    workflow.description = body.description.strip()
    workflow.operations = body.operations
    workflow.version += 1
    workflow.updated_at = utcnow()
    db.commit()
    return workflow_out(workflow)


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    require_project(db, user, workflow.project_id, "editor")
    db.delete(workflow)
    db.commit()
    return {"ok": True}


@router.post("/workflows/{workflow_id}/run")
def run_workflow(workflow_id: str, body: RunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    require_project(db, user, workflow.project_id, "editor")
    if not body.asset_ids:
        raise HTTPException(status_code=400, detail="Choose images to process")
    known = db.query(Asset.id).filter(Asset.id.in_(body.asset_ids), Asset.project_id == workflow.project_id).count()
    if known != len(set(body.asset_ids)):
        raise HTTPException(status_code=400, detail="One of those images is not in this project")
    job = create_job(
        db,
        project_id=workflow.project_id,
        user_id=user.id,
        kind="batch",
        payload={"workflow_id": workflow.id, "asset_ids": body.asset_ids, "seed": body.seed, "dry_run": body.dry_run},
    )
    job = enqueue(db, job)
    return job_out(job)


@router.post("/projects/{project_id}/workflow-templates")
def save_workflow_template(project_id: str, body: TemplateIn, workflow_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    workflow = db.get(Workflow, workflow_id)
    if workflow is None or workflow.project_id != project.id:
        raise HTTPException(status_code=404, detail="Workflow not found")
    template = WorkflowTemplate(user_id=user.id, name=body.name.strip(), description=workflow.description, operations=workflow.operations)
    db.add(template)
    db.commit()
    db.refresh(template)
    return {"id": template.id, "name": template.name}


@router.get("/workflow-templates")
def list_workflow_templates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(WorkflowTemplate).filter_by(user_id=user.id).order_by(WorkflowTemplate.created_at.desc()).all()
    return [{"id": row.id, "name": row.name, "description": row.description, "operations": row.operations} for row in rows]


@router.post("/projects/{project_id}/workflow-templates/{template_id}/apply")
def apply_workflow_template(project_id: str, template_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id, "editor")
    template = db.get(WorkflowTemplate, template_id)
    if template is None or template.user_id != user.id:
        raise HTTPException(status_code=404, detail="Template not found")
    workflow = Workflow(project_id=project.id, name=template.name, description=template.description, operations=template.operations)
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow_out(workflow)


@router.get("/projects/{project_id}/jobs")
def list_jobs(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, _role = require_project(db, user, project_id)
    rows = db.query(Job).filter_by(project_id=project.id).order_by(Job.created_at.desc()).limit(50).all()
    return [job_out(row) for row in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    require_project(db, user, job.project_id)
    return job_out(job)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    require_project(db, user, job.project_id, "editor")
    job.status = "queued"
    job.error = None
    job.attempts = 0
    job.progress = 0
    job = enqueue(db, job)
    return job_out(job)
