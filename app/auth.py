"""T-039 · Verificación de JWT de Supabase Auth y aislamiento por usuario.

Este módulo proporciona la dependencia `get_current_user` que:

1. Extrae el token Bearer del header `Authorization`.
2. Verifica la firma del JWT contra las JWKS públicas de Supabase (RS256).
3. Valida `iss` (issuer) y `aud` (audience = "authenticated").
4. Devuelve el UUID del usuario (`sub`) y el email.

Si no hay token o es inválido, responde 401.

Las JWKS se cachean en memoria (TTL 1 h) para evitar una petición HTTP
por cada request.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
from fastapi import Header, HTTPException, status
from jwt import PyJWKClient

from app.config import get_settings

# ---------------------------------------------------------------------------
# Cache de JWKS (Json Web Key Set) de Supabase
# ---------------------------------------------------------------------------

_jwks_client: PyJWKClient | None = None
_jwks_fetched_at: float = 0
_JWKS_TTL = 3600  # 1 hora


def _get_jwks_client() -> PyJWKClient:
    """Devuelve (y cachea) el cliente JWKS de Supabase."""
    global _jwks_client, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_client is None or (now - _jwks_fetched_at) > _JWKS_TTL:
        supabase_url = get_settings().supabase_url_value.rstrip("/")
        jwks_uri = f"{supabase_url}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_uri)
        _jwks_fetched_at = now
    return _jwks_client


def _verify_token(token: str) -> dict[str, Any]:
    """Verifica un JWT de Supabase y devuelve sus claims."""
    settings = get_settings()
    supabase_url = settings.supabase_url_value.rstrip("/")
    # El issuer real de Supabase no lleva slash final (ver .well-known/openid-configuration).
    expected_issuer = f"{supabase_url}/auth/v1"

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            # Supabase puede firmar con ES256, RS256 o HS256 según el proyecto.
            # El algoritmo concreto se infiere del `kid` de las JWKS.
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=expected_issuer,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token ha expirado. Inicia sesión de nuevo.",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {exc}",
        )
    return payload


# ---------------------------------------------------------------------------
# Dependencia de FastAPI
# ---------------------------------------------------------------------------


def get_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Dependencia que verifica el JWT y devuelve los claims del usuario.

    Uso:
        def endpoint(usuario = Depends(get_current_user)):
            uid = usuario["sub"]  # UUID del usuario

    Si se usa a nivel de router (`dependencies=[Depends(get_current_user)]`)
    solo verifica que el token sea válido, sin dar acceso al objeto.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el header Authorization: Bearer <token>.",
        )
    token = authorization.removeprefix("Bearer ").strip()
    return _verify_token(token)
