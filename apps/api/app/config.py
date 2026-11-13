from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", API_ROOT / ".env"),
        extra="ignore",
    )

    database_url: str = f"sqlite:///{API_ROOT / 'nftstudio.db'}"
    storage_dir: str = ""
    secret_key: str = "dev-only-change-me-please-use-a-long-secret"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    embed_worker: bool = True
    force_sync: bool = False
    seed_demo: bool = True
    allow_plan_switch: bool = True
    redis_url: str = ""
    celery_enabled: bool = False
    ai_endpoint: str = ""
    max_upload_mb: int = 30
    token_days: int = 14
    signed_url_hours: int = 12
    public_base_url: str = "http://localhost:8000"

    @property
    def cors_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_dir) if self.storage_dir else REPO_ROOT / "storage"
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


PLANS: dict[str, dict] = {
    "free": {
        "label": "Free",
        "projects": 3,
        "supply": 100,
        "automation": True,
        "ai": False,
        "credits": 20,
        "price": 0,
        "blurb": "Editing, trait setup, and small collections.",
    },
    "creator": {
        "label": "Creator",
        "projects": 15,
        "supply": 2000,
        "automation": True,
        "ai": True,
        "credits": 200,
        "price": 19,
        "blurb": "Larger drops and basic automation credits.",
    },
    "pro": {
        "label": "Pro",
        "projects": 50,
        "supply": 10000,
        "automation": True,
        "ai": True,
        "credits": 2000,
        "price": 49,
        "blurb": "AI credits, batch automation, and bigger supplies.",
    },
    "studio": {
        "label": "Studio",
        "projects": 200,
        "supply": 50000,
        "automation": True,
        "ai": True,
        "credits": 10000,
        "price": 149,
        "blurb": "Team roles, shared workflows, and high limits.",
    },
}
