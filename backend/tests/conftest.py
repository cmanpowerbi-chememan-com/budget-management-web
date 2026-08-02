"""Shared pytest fixtures for backend unit tests."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.sap import clear_sap_caches


@pytest.fixture
def client():
    """TestClient with a clean dependency-override slate per test."""
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _hermetic_unit_settings(request, monkeypatch):
    """The unit suite must never depend on the developer's backend/.env or
    process env. Two leaks bit in practice (2026-07-20 gate LOW):

    - APP_ENV=local + DEV_AUTH_EMAIL (the documented local setup, see
      backend/.env.example) made every `*_401_without_auth` test return the
      dev email instead of 401 — green CI, red local.
    - GL_EDIT_BY_ENABLED=true made write_model's GL lookup select a 3rd
      column the tests' 2-tuple cursor mocks never provide (IndexError).
    - SAP_CACHE_TTL_SECONDS defaulting to the real 600s would make the
      module-level SAP cache (app.sap) silently serve one test's mocked
      figures to the next test — must be forced to 0 (cache disabled) here.
    - WARMUP_ENABLED defaulting to True would fire the startup warmup
      thread against the live DB the moment `TestClient(app)` runs the
      app's lifespan (conftest's `client` fixture does exactly that).

    Integration-marked tests keep the real env — they exist to talk to the
    live DB with the developer's own credentials/settings."""
    if request.node.get_closest_marker("integration"):
        yield
        return
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEV_AUTH_EMAIL", raising=False)
    monkeypatch.setenv("GL_EDIT_BY_ENABLED", "false")
    monkeypatch.setenv("SAP_CACHE_TTL_SECONDS", "0")
    monkeypatch.setenv("WARMUP_ENABLED", "false")
    get_settings.cache_clear()
    # FastAPI-DI settings also skip the .env file: the real auth dependency
    # must raise 401 without an Easy Auth header, never read DEV_AUTH_EMAIL.
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    yield
    app.dependency_overrides.pop(get_settings, None)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clear_sap_caches_every_test():
    """A module-level TTL cache keyed only by `fiscal_year` (app.sap) would
    otherwise leak a mocked result from one test into another — including
    integration tests, which is why this fixture (unlike the hermetic
    settings one above) does NOT early-return on the `integration` marker."""
    clear_sap_caches()
    yield
    clear_sap_caches()
