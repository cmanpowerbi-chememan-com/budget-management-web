"""App configuration — env-driven settings.

Fail-closed default: APP_ENV defaults to "production" so a missing/blank
env var never accidentally enables the local DEV auth override (ADR-0004).

env re-point note (ADR-0023): FABRIC_SQL_SERVER / FABRIC_SQL_DATABASE must be
pointed at `fabric_sql_database` (the DW SQL DB, budget.* + dbo.* schemas)
once the user re-points env — this app never hardcodes a host, it only reads
env vars. That re-point is a deploy-time config change, not done here.
"""
import logging
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Anchor to backend/.env regardless of cwd. Without this, running uvicorn/pytest
# from the repo root would silently load the repo-root .env instead — which still
# points at the retired DB1 Azure SQL (ADR-0023) — a silent wrong-database footgun.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# The out-of-the-box `app_base_url` value (ADR-0016) — a real placeholder,
# not a live URL (the app is not deployed yet, CLAUDE.md). Kept as a named
# constant so the misconfiguration guard below and its test compare against
# the exact same value as the field default, never a duplicated literal.
_DEFAULT_APP_BASE_URL = "https://budget.chememan.com"


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

    # A12 notifications (Graph sendMail) — fail-safe default TRUE (never-cut
    # safety rule): every notify_* call is a log-only preview unless this is
    # explicitly flipped, a deliberate go-live config change by jakkaritw,
    # never touched by this build or by any test.
    notifications_dry_run: bool = True

    # Convenience-only deep-link base (ADR-0016) — placeholder default OK,
    # flagged: the React+FastAPI app is not deployed yet (CLAUDE.md), so this
    # is the intended production domain, not a live URL today.
    app_base_url: str = _DEFAULT_APP_BASE_URL

    # A10 attachments (R1, docs/specs/budget-transactional-data-model.md §4b) —
    # SharePoint site/library/root-folder for `เอกสาร ฝ่าย/<ฝ่าย>/<year>/`.
    # These are NOT a guess: site `CMANDWPRD` / library `Budgeting and
    # Management` / folder `เอกสาร ฝ่าย` were confirmed 2026-07-13 (spec §4b,
    # ADR-0018) — the same site/library the 8 admin-master Excel syncs use.
    # Kept as overridable settings (never hardcoded in attachments.py) so a
    # wrong value can be corrected via env without a code change; a blank
    # override still fails loud via AttachmentsNotConfiguredError rather than
    # silently guessing a location (see app/attachments.py).
    attachments_site_hostname: str = "chememan.sharepoint.com"
    attachments_site_name: str = "CMANDWPRD"
    attachments_library_name: str = "Budgeting and Management"
    attachments_root_folder: str = "เอกสาร ฝ่าย"

    # GL `edit_by` admin-only lock (design v2, 2026-07-17) — OFF by default:
    # while False, no code path in this app ever SELECTs `dbo.gl_group.edit_by`
    # or changes behavior at all. jakkaritw flips this on when ready to go
    # live with the 13 secret admin-only GLs (Insurance Premium, Employee
    # benefits severance, Depreciation).
    gl_edit_by_enabled: bool = False

    # A14 — built SPA location (`frontend/dist`), ONE Container App serves
    # both API + frontend. In the container this will be an absolute path
    # (e.g. /app/static); unset locally, where it falls back to the sibling
    # `frontend/dist` so a local `uvicorn` run can preview a production build
    # without any extra config. Missing dir = API-only, no error (app/static.py).
    static_dir: str | None = None

    @property
    def static_dir_path(self) -> Path:
        if self.static_dir:
            return Path(self.static_dir)
        # backend/app/config.py -> backend/ -> repo root -> frontend/dist
        return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

    @property
    def is_local(self) -> bool:
        return self.app_env.strip().lower() == "local"

    @property
    def admin_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    def _warn_if_production_placeholder_base_url(self) -> None:
        """Misconfiguration guard: `app_base_url` is meant to be overridden
        with the real deployed domain before go-live. If `app_env` is
        production and it is still the out-of-the-box placeholder, nobody
        set `APP_BASE_URL` for this deploy — warn loudly so it surfaces in
        logs, but never raise (a wrong base URL only degrades the deep-link
        convenience feature, ADR-0016; it must not block app boot)."""
        if self.app_env.strip().lower() == "production" and self.app_base_url == _DEFAULT_APP_BASE_URL:
            logger.warning(
                "app_base_url is still the placeholder default (%s) while app_env=production — "
                "set APP_BASE_URL to the real deployed domain before go-live",
                _DEFAULT_APP_BASE_URL,
            )

    def model_post_init(self, __context: object) -> None:
        """Runs once per Settings load (pydantic v2 hook) — see
        `_warn_if_production_placeholder_base_url`."""
        self._warn_if_production_placeholder_base_url()


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Call get_settings.cache_clear() in tests
    that mutate env vars between assertions."""
    return Settings()
