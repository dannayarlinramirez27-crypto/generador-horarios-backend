from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health", tags=["system"])
def health() -> dict:
    """Probar que el servidor está vivo (sin tocar la base de datos)."""
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}