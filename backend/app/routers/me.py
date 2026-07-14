"""GET /me — auth smoke test. Returns the resolved identity + APP_ENV."""
from fastapi import APIRouter, Depends

from app.auth import get_current_user_email
from app.config import Settings, get_settings

router = APIRouter()


@router.get("/me")
def me(
    email: str = Depends(get_current_user_email),
    settings: Settings = Depends(get_settings),
) -> dict:
    return {"email": email, "app_env": settings.app_env}
