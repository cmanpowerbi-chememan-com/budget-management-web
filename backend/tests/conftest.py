"""Shared pytest fixtures for backend unit tests."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture
def client():
    """TestClient with a clean dependency-override slate per test."""
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()
