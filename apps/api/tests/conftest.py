import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["STORAGE_DIR"] = str(_tmp / "storage")
os.environ["EMBED_WORKER"] = "0"
os.environ["SEED_DEMO"] = "0"
os.environ["FORCE_SYNC"] = "1"
os.environ["SECRET_KEY"] = "test-secret-key-with-enough-length"
os.environ["ALLOW_PLAN_SWITCH"] = "1"
os.environ["PUBLIC_BASE_URL"] = "http://localhost:8000"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


def auth(client, email="artist@example.com", name="Ada"):
    response = client.post("/api/auth/register", json={"name": name, "email": email, "password": "studio-pass"})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}
