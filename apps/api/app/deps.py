from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import PLANS
from app.database import SessionLocal
from app.models import Project, ProjectMember, UsageEvent, User
from app.security import decode_token


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    token = authorization.split(" ", 1)[1].strip()
    try:
        user_id = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Session expired") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired")
    return user


ROLE_RANK = {"reviewer": 1, "editor": 2, "owner": 3}


def require_project(db: Session, user: User, project_id: str, min_role: str = "reviewer") -> tuple[Project, str]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id == user.id:
        role = "owner"
    else:
        member = db.query(ProjectMember).filter_by(project_id=project.id, user_id=user.id).one_or_none()
        if member is None:
            raise HTTPException(status_code=404, detail="Project not found")
        role = member.role
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise HTTPException(status_code=403, detail="You do not have permission for this action")
    return project, role


def plan_limits(user: User) -> dict:
    return PLANS.get(user.plan, PLANS["free"])


def assert_can_create_project(db: Session, user: User) -> None:
    limit = plan_limits(user)["projects"]
    count = db.query(Project).filter_by(owner_id=user.id).count()
    if count >= limit:
        raise HTTPException(status_code=402, detail=f"The {user.plan} plan includes {limit} projects")


def assert_supply(user: User, supply: int) -> None:
    limit = plan_limits(user)["supply"]
    if supply < 1 or supply > limit:
        raise HTTPException(status_code=402, detail=f"The {user.plan} plan generates up to {limit} NFTs per collection")


def record_usage(db: Session, user: User, kind: str, units: int, project_id: str | None = None, detail: str = "") -> None:
    db.add(UsageEvent(user_id=user.id, project_id=project_id, kind=kind, units=units, detail=detail))


def charge_credits(db: Session, user: User, units: int, kind: str, project_id: str | None, detail: str = "") -> None:
    if user.credits < units:
        raise HTTPException(status_code=402, detail="Not enough AI credits for this run")
    user.credits -= units
    record_usage(db, user, kind, units, project_id, detail)
