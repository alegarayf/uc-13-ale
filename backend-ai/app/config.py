from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT / ".env", extra="ignore")

    environment: str = "development"
    cors_origins: str = "*"

    databricks_host: str = ""
    databricks_token: str = ""
    databricks_genie_space_id: str = ""

    # auto | mock | genie
    rules_ai_mode: str = "auto"
    rules_config_dir: Path = _REPO_ROOT / "rules-config"
    rules_ai_max_denies: int = 1


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Align with backend-api env names when dedicated AI vars are unset.
    import os

    if not settings.databricks_host:
        settings.databricks_host = os.getenv("DATABRICKS_SERVER_HOSTNAME", "")
    if not settings.databricks_token:
        settings.databricks_token = os.getenv("DATABRICKS_TOKEN", "")
    if not settings.databricks_genie_space_id:
        settings.databricks_genie_space_id = os.getenv("DATABRICKS_GENIE_SPACE_ID", "")
    return settings


def resolve_rules_ai_mode(settings: Settings) -> str:
    mode = settings.rules_ai_mode.lower()
    if mode in ("mock", "genie"):
        return mode
    if settings.databricks_genie_space_id and settings.databricks_token and settings.databricks_host:
        return "genie"
    return "mock"
