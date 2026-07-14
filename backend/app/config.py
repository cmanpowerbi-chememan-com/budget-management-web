"""App configuration — env-driven settings.

Fail-closed default: APP_ENV defaults to "production" so a missing/blank
env var never accidentally enables the local DEV auth override (ADR-0004).

env re-point note (ADR-0023): FABRIC_SQL_SERVER / FABRIC_SQL_DATABASE must be
pointed at `fabric_sql_database` (the DW SQL DB, budget.* + dbo.* schemas)
once the user re-points env — this app never hardcodes a host, it only reads
env vars. That re-point is a deploy-time config change, not done here.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor to backend/.env regardless of cwd. Without this, running uvicorn/pytest
# from the repo root would silently load the repo-root .env instead — which still
# points at the retired DB1 Azure SQL (ADR-0023) — a silent wrong-database footgun.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Env-driven settings. Unknown env vars (e.g. the repo-root .env's legacy
    Azure SQL vars) are ignored rather than rejected."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_env: str = "production"

    # Local-only Easy Auth override — honored ONLY when app_env == "local".
    dev_auth_email: str | None = None

    # Fabric SQL Database — ONE DB, budget.* (transactional) + dbo.* (masters/employee) schemas.
    fabric_sql_server: str | None = None
    fabric_sql_database: str | None = None

    # SAP gold warehouse — read-only, separate connection.
    gold_sql_server: str | None = None
    gold_sql_database: str | None = None

    # Service Principal `cman-fabric-write` (shared SP; app-layer RLS, ADR-0019).
    entra_client_id: str | None = None
    entra_client_secret: str | None = None
    entra_tenant_id: str | None = None

    # Admin allowlist overlay (ADR-0012/0014) — comma-separated emails, e.g.
    # "jakkaritw@chememan.com,nipapornt@chememan.com". Checked BEFORE any
    # scope membership; grants is_admin regardless of Fill/See scope.
    admin_emails: str = ""

    @property
    def is_local(self) -> bool:
        return self.app_env.strip().lower() == "local"

    @property
    def admin_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Call get_settings.cache_clear() in tests
    that mutate env vars between assertions."""
    return Settings()
