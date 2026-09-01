"""T-039 · Verificación de JWT de Supabase Auth y aislamiento por usuario.

Este módulo proporciona la dependencia `get_current_user` que:

1. Extrae el token Bearer del header `Authorization`.
2. Verifica la firma del JWT contra las JWKS públicas de Supabase (ES256/RS256).
3. Valida `iss` (issuer) y `aud` (audience = "authenticated").
4. Devuelve el UUID del usuario (`sub`) y el email.

Si no hay token o es inválido, responde 401.

Las JWKS se cachean en memoria (TTL 1 h) para evitar una petición HTTP
por cada request.

RBAC (Role-Based Access Control):
- `require_roles(allowed_roles)`: dependencia que valida el token y extrae el rol.
- Roles del sistema:
  - "admin": Acceso total (crear, editar, generar y ver horarios).
  - "docente": Solo lectura de los horarios donde esté asignado.
  - "estudiante": Solo lectura del horario perteneciente a su curso.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status
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
        # Timeout de 10s: si Render no puede alcanzar Supabase, fallamos
        # rápido con un 503 en vez de colgarse la petición.
        _jwks_client = PyJWKClient(jwks_uri, timeout=10)
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
    except Exception as exc:
        # Error de red al fetchear las JWKS, o cualquier otro problema
        # inesperado: 503 para distinguirlo de un token inválido (401).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo verificar el token contra Supabase: {exc}",
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


def _extract_role(claims: dict[str, Any]) -> str:
    """Extrae el rol del usuario desde los claims del JWT de Supabase.

    Busca en orden de prioridad:
    1. `user_metadata.role` (custom claims definidos al registrar usuario)
    2. `app_metadata.role` (claims administrativos de Supabase)
    3. `role` (claim personalizado directo)
    4. Por defecto: "estudiante" (rol menos privilegiado)
    """
    # user_metadata: claims que el usuario puede modificar (ej. en signup)
    user_meta = claims.get("user_metadata", {})
    if isinstance(user_meta, dict) and user_meta.get("role"):
        return str(user_meta["role"])

    # app_metadata: claims que solo admins de Supabase pueden modificar
    app_meta = claims.get("app_metadata", {})
    if isinstance(app_meta, dict) and app_meta.get("role"):
        return str(app_meta["role"])

    # Claim directo 'role' si existe
    if claims.get("role"):
        return str(claims["role"])

    # Default: rol menos privilegiado
    return "estudiante"


def get_current_user_role(
    usuario: dict[str, Any] = Depends(get_current_user),
) -> str:
    """Dependencia que devuelve el rol del usuario autenticado."""
    return _extract_role(usuario)


def require_roles(allowed_roles: list[str]):
    """Dependencia de fábrica que valida el token y exige uno de los roles permitidos.

    Uso:
        @router.post("/generar", dependencies=[Depends(require_roles(["admin"]))])
        def generar(...):

    Lanza 403 si el usuario autenticado no tiene ninguno de los roles permitidos.
    """
    def _check_role(usuario: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        role = _extract_role(usuario)
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: se requiere uno de los roles {allowed_roles}, tienes '{role}'.",
            )
        return usuario
    return _check_role
