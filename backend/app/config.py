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

# The shared reporting mailbox. jakkaritw, 2026-08-09: it plays THREE roles at
# once, and they must never drift apart, so all three read this one constant:
#   1. the mailbox every notification is sent AS (`notifications_sender_email`),
#   2. the mailbox cc'd on EVERY notification (`notifications_audit_cc_email`),
#      so the whole mail trail is searchable in one inbox — not only in Sent Items,
#   3. a full admin, in EVERY environment (`admin_emails_set` below).
# Role 3 is deliberately code-level, not env-level: ADMIN_EMAILS is set per
# container, so an env-only grant would silently exist on staging and be missing
# on production (or vice versa) the first time someone edits one and not the other.
SHARED_ADMIN_MAILBOX = "cmanpowerbi@chememan.com"


class Settings(BaseSettings):
    """Env-driven settings. Unknown env vars (e.g. the repo-root .env's legacy
    Azure SQL vars) are ignored rather than rejected."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_env: str = "production"

    # Local-only Easy Auth override — honored ONLY when app_env == "local".
    dev_auth_email: str | None = None

    # SIT/UAT test aid (2026-08-10, grammar + guard extended 2026-08-17):
    # rewrites one resolved Easy Auth identity to one of a configured list of
    # targets, e.g. "jakkaritw@chememan.com:nipapornt@chememan.com,warapornt@chememan.com"
    # (the old single-target "from:to" form still works, a 1-target list).
    # Which target applies is picked per browser session by the `sit_as`
    # cookie (default = the first target) — see `app.routers.sit` and
    # `app.auth._select_sit_target`. Lets a tester with no employee row act
    # as ANY of the configured approvers on staging, where header spoofing no
    # longer works against real Easy Auth.
    #
    # Honored ONLY when THREE conditions all hold (`app.auth._sit_guard_ok`):
    # (1) HARD `app_env != "production"` (dead on PRD, which runs
    # app_env=production, checked first, absolute); (2) the resolved caller
    # email is in `admin_emails_set` (2026-08-17 — replaces the old
    # `notifications_environment_label` non-blank check: staging now removes
    # that label entirely so SIT mail looks byte-identical to production, no
    # test banner/subject prefix — so it can no longer double as a
    # non-production signal here); (3) this value is set and well-formed.
    # Condition 2 alone only rules out non-admins — it is NOT "any admin
    # may impersonate": the caller must additionally equal this value's own
    # `from_email` (enforced by `app.auth.sit_targets_for` /
    # `_apply_sit_impersonation`), so a different admin is refused too
    # (2026-08-18 gate fix — do not loosen this to match the old, wrong
    # reading). Never set this on PRD.
    sit_impersonate: str = ""

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

    # Mailbox every app notification is sent AS (`POST /users/{sender}/sendMail`).
    # jakkaritw picked the shared reporting mailbox on 2026-08-02 so recipients
    # see "CMAN_PowerBI", not a personal name, and Reply lands in a shared inbox
    # instead of his own (the old value was jakkaritw@chememan.com). Mail.Send is
    # an APPLICATION role, so no per-mailbox grant is needed — sending as
    # cmanpowerbi verified live (Graph 202) the same day.
    notifications_sender_email: str = SHARED_ADMIN_MAILBOX

    # Non-production mail marking (jakkaritw, 2026-08-09: "หัวเมลทดสอบที่ stg
    # ระบุว่า ทดสอบตัวใหญ่ๆ"). When set, EVERY notification gets this label
    # shouted in the subject line and a full-width red banner at the top of the
    # body, so a real colleague who receives a staging mail cannot mistake it
    # for a live approval request. Blank (the default) = production behaviour,
    # no marking at all — so forgetting to set it in prd is the safe direction.
    notifications_environment_label: str = ""

    # Mail catcher for non-production (same 2026-08-09 change). When set, EVERY
    # notification is delivered to this ONE address instead of the recipient the
    # app resolved, and all cc is dropped; the banner then prints the real To/cc
    # it WOULD have used. This is what makes it safe to run staging with
    # `notifications_dry_run=False`: the full Graph send path is exercised for
    # real, but no live colleague is emailed by a test. Blank = deliver normally.
    notifications_redirect_all_to: str = ""

    # Blind-copy-style audit trail (jakkaritw, 2026-08-09): EVERY notification
    # cc's this mailbox, on top of whatever cc the individual mail already
    # carries (reject/final-approve cc the frozen approver1, reminders cc the
    # derived approver1). Sent Items alone was not enough — a cc'd copy lands in
    # the Inbox where it is searchable and shareable. Set to "" to switch the
    # audit copy off without a code change; `notifications.send_mail` also drops
    # it when it would duplicate the To or an existing cc.
    notifications_audit_cc_email: str = SHARED_ADMIN_MAILBOX

    # §7.3 bulk-send hardening (jobs/send_reminders.py only — event mails
    # from the router never sleep): pacing between reminder mails so one
    # round can't ram the Exchange Online throttle (~30/min/mailbox), and a
    # PER-PHASE cap on sends per run (0 = unlimited); over-cap recipients
    # are skipped loudly ("capped N" log line) and simply re-reminded next
    # run, since no reminder_log row is written for them.
    reminder_send_delay_seconds: float = 2.0
    reminder_max_sends_per_run: int = 150

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
    # live with the 12 admin-only GLs (Insurance Premium ×9, Depreciation,
    # Employee benefits severance ×2 — count confirmed by
    # gl-editby-6211300999-forensics: the budget dept owner deliberately set
    # 6211300999 to user, so 12 is the intended number, not 13).
    gl_edit_by_enabled: bool = False

    # SAP gold-read TTL cache (perf fix — prod first-load 10-11s -> 2-3s,
    # see app.cache + app.sap's `*_cached` wrappers): both gold reads
    # (`fetch_sap_actuals` ~0.60s, `resolve_sap_coverage`'s entry-day query
    # ~1.22s, live-measured) cost real time on EVERY grid/coverage request
    # even though the answer only changes when new SAP data lands. `0`
    # disables caching entirely (always hits the DB) — the test/kill-switch
    # path; the hermetic test fixture sets this to 0 for every unit test.
    sap_cache_ttl_seconds: int = 600

    # Connection-pool + SAP-cache warmup at startup (perf fix, see
    # app.main's lifespan handler): runs in a daemon thread so it never
    # blocks app startup / the Container Apps probe. Gate so tests (which
    # run the app's lifespan via TestClient) never hit a live DB.
    warmup_enabled: bool = True

    # Root logger level (see `app/logging_config.py`) — every `app.*` logger
    # writes at this level and above to the container's stdout. Overridable
    # so a live debug session can bump to DEBUG, or a noisy deploy can be
    # dialed down to WARNING, without a code change.
    log_level: str = "INFO"

    # A14 — built frontend location (`frontend/out`, Next.js static export;
    # previously `frontend/dist` under Vite). ONE Container App serves both
    # API + frontend. In the container this will be an absolute path (e.g.
    # /app/static); unset locally, where it falls back to the sibling
    # `frontend/out` so a local `uvicorn` run can preview a production build
    # without any extra config. Missing dir = API-only, no error (app/static.py).
    static_dir: str | None = None

    @property
    def static_dir_path(self) -> Path:
        if self.static_dir:
            return Path(self.static_dir)
        # backend/app/config.py -> backend/ -> repo root -> frontend/out
        return Path(__file__).resolve().parent.parent.parent / "frontend" / "out"

    @property
    def is_local(self) -> bool:
        return self.app_env.strip().lower() == "local"

    @property
    def admin_emails_set(self) -> set[str]:
        """The env allowlist PLUS the shared reporting mailbox, which is an
        admin in every environment by construction (jakkaritw, 2026-08-09) —
        see `SHARED_ADMIN_MAILBOX`. Union, never replace: a deploy that forgets
        ADMIN_EMAILS still leaves the shared mailbox able to act, and a deploy
        that lists it explicitly does not end up with a duplicate."""
        env_admins = {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}
        return env_admins | {SHARED_ADMIN_MAILBOX.lower()}

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
