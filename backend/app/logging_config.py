"""Root logger setup — see `configure_logging`.

Without this, every `app.*` module's `logger.info(...)`/`logger.warning(...)`
call is silently dropped in production: uvicorn only installs handlers on
its OWN loggers (`uvicorn`, `uvicorn.access`) and sets `propagate=False` on
both (verified against the installed uvicorn's `LOGGING_CONFIG`), so it
never touches the root logger — which defaults to level WARNING with no
handler at all, meaning even a WARNING-level record from `app/*` has
nowhere to go.
"""
import logging
import sys

# Named so `configure_logging` can recognize "already installed" without a
# module-level "did we run yet" flag (see its docstring).
_HANDLER_NAME = "app-root-stream-handler"


def configure_logging(level: str = "INFO") -> None:
    """Attach one stdout handler to the root logger so `app.*` log records
    at `level` and above reach the container log.

    A single `StreamHandler`-based setup (the shape of `logging.basicConfig`)
    is deliberate: this app has one log destination (stdout, collected by
    Container Apps) and one format, so a `dictConfig` would only add
    indirection with no behavioral difference — the project favors the
    simpler option when both do the same job (CLAUDE.md project philosophy).

    Idempotent by construction rather than by a "did we already run" flag:
    it checks the root logger's actual handlers for one named
    `_HANDLER_NAME` before adding another, so calling this more than once
    (e.g. once from `app.main` at import time, again from a test) never
    duplicates output. The level is always (re)applied even when the
    handler already exists, so an env override still takes effect.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if any(handler.name == _HANDLER_NAME for handler in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.name = _HANDLER_NAME
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    root.addHandler(handler)
