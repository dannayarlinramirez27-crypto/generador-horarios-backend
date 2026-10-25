"""Authenticated current-user profile and trusted role resolution."""

from typing import Any

import psycopg
from fastapi import APIRouter, Depends

from app.auth import _extract_docente_id_from_email, _extract_role, get_current_user
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.get("/me")
def current_user_profile(
    usuario: dict[str, Any] = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Return the backend-resolved role and email-linked docente identifier."""
    role = _extract_role(usuario, conn)
    return {
        "role": role,
        "docente_id": (
            _extract_docente_id_from_email(conn, usuario.get("email"))
            if role == "docente"
            else None
        ),
    }
