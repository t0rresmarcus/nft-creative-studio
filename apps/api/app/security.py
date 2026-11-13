import base64
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet

from app.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.token_days),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> str:
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    return str(payload["sub"])


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def sign_asset_url(asset_id: str, variant: str = "full") -> str:
    expires = int(time.time()) + settings.signed_url_hours * 3600
    message = f"{asset_id}.{variant}.{expires}".encode()
    signature = hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()
    return f"/api/files/{asset_id}?variant={variant}&expires={expires}&signature={signature}"


def verify_asset_signature(asset_id: str, variant: str, expires: int, signature: str) -> bool:
    if expires < int(time.time()):
        return False
    message = f"{asset_id}.{variant}.{expires}".encode()
    expected = hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
