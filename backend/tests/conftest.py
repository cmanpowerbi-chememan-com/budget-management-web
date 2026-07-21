"""Shared pytest fixtures for backend unit tests."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


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

    Integration-marked tests keep the real env — they exist to talk to the
    live DB with the developer's own credentials/settings."""
    if request.node.get_closest_marker("integration"):
        yield
        return
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEV_AUTH_EMAIL", raising=False)
    monkeypatch.setenv("GL_EDIT_BY_ENABLED", "false")
    get_settings.cache_clear()
    # FastAPI-DI settings also skip the .env file: the real auth dependency
    # must raise 401 without an Easy Auth header, never read DEV_AUTH_EMAIL.
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    yield
    app.dependency_overrides.pop(get_settings, None)
    get_settings.cache_clear()
