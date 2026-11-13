from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import PLANS
from app.deps import charge_credits, get_current_user, get_db, record_usage
from app.models import UsageEvent, User
from app.schemas import IpfsIn, LoginIn, PlanIn, RegisterIn
from app.security import create_token, decrypt_secret, encrypt_secret, hash_password, utcnow, verify_password
from app.serializers import user_out

router = APIRouter(prefix="/api")

_attempts: dict[str, list[float]] = {}


def _valid_email(email: str) -> bool:
    return "@" in email and "." in email.split("@")[-1] and len(email) <= 255


def _throttle(email: str) -> None:
    import time

    now = time.time()
    bucket = [stamp for stamp in _attempts.get(email, []) if now - stamp < 60]
    if len(bucket) >= 12:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait a minute and try again.")
    bucket.append(now)
    _attempts[email] = bucket


@router.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not _valid_email(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if db.query(User).filter_by(email=email).one_or_none():
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password), plan="free", credits=PLANS["free"]["credits"])
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id), "user": user_out(user)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    _throttle(email)
    user = db.query(User).filter_by(email=email).one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return {"token": create_token(user.id), "user": user_out(user)}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.get("/account")
def account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models import Project

    events = db.query(UsageEvent).filter_by(user_id=user.id).order_by(UsageEvent.created_at.desc()).limit(30).all()
    return {
        "user": user_out(user),
        "plans": PLANS,
        "usage": {
            "projects": db.query(Project).filter_by(owner_id=user.id).count(),
            "project_limit": PLANS[user.plan]["projects"],
            "supply_limit": PLANS[user.plan]["supply"],
            "credits": user.credits,
        },
        "events": [
            {"kind": event.kind, "units": event.units, "detail": event.detail, "created_at": event.created_at.isoformat()}
            for event in events
        ],
    }


@router.post("/account/plan")
def switch_plan(body: PlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.config import settings

    if not settings.allow_plan_switch:
        raise HTTPException(status_code=403, detail="Plan changes are managed outside this server")
    if body.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")
    user.plan = body.plan
    user.credits = PLANS[body.plan]["credits"]
    record_usage(db, user, "plan", 0, detail=body.plan)
    db.commit()
    return user_out(user)


@router.put("/account/ipfs")
def save_ipfs(body: IpfsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.pinata_jwt.strip():
        user.ipfs_secret = None
    else:
        user.ipfs_secret = encrypt_secret(body.pinata_jwt.strip())
    db.commit()
    return {"ipfs_configured": bool(user.ipfs_secret)}


@router.delete("/account/ipfs")
def clear_ipfs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.ipfs_secret = None
    db.commit()
    return {"ipfs_configured": False}
