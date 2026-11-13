from app.config import PLANS, settings
from app.database import SessionLocal
from app.models import Project, User, Workflow
from app.security import hash_password
from app.services.library import build_sample_layers

DEMO_EMAIL = "demo@nftstudio.local"
DEMO_PASSWORD = "demo-studio-123"


def seed_demo() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=DEMO_EMAIL).one_or_none()
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                name="Demo Artist",
                password_hash=hash_password(DEMO_PASSWORD),
                plan="pro",
                credits=PLANS["pro"]["credits"],
            )
            db.add(user)
            db.flush()
        project = db.query(Project).filter_by(owner_id=user.id, name="Signal Portraits").one_or_none()
        if project is None:
            project = Project(
                owner_id=user.id,
                name="Signal Portraits",
                description="A sample generative collection with four layers. Plan it, render it, then export.",
                project_type="generative",
                canvas_width=640,
                canvas_height=640,
                license="cc-by",
                ai_disclosure="Sample layers in this demo project were drawn by the studio, not by a generative model.",
            )
            db.add(project)
            db.flush()
            build_sample_layers(db, project, user.id, replace=False)
            db.add(
                Workflow(
                    project_id=project.id,
                    name="Square sharpen",
                    description="Cover-crop to the canvas and sharpen. Reuse it on a photo set.",
                    operations=[
                        {"type": "resize", "params": {"width": 640, "height": 640, "fit": "cover"}},
                        {"type": "sharpen", "params": {}},
                        {"type": "format", "params": {"format": "png"}},
                        {"type": "rename", "params": {"pattern": "{project}-{index}"}},
                    ],
                )
            )
        db.commit()
    finally:
        db.close()


def maybe_seed() -> None:
    if settings.seed_demo:
        seed_demo()
