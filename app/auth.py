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
import psycopg
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient
from psycopg.rows import dict_row

from app.config import get_settings
from app.db import get_db

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


def _extract_role_from_claims(claims: dict[str, Any]) -> str:
    """Fallback: extrae el rol desde los claims del JWT de Supabase.

    Busca en orden de prioridad:
    1. `user_metadata.role` (custom claims definidos al registrar usuario)
    2. `app_metadata.role` (claims administrativos de Supabase)
    3. `role` (claim personalizado directo)
    4. Por defecto: "estudiante" (rol menos privilegiado)
    """
    user_meta = claims.get("user_metadata", {})
    if isinstance(user_meta, dict) and user_meta.get("role"):
        return str(user_meta["role"])

    app_meta = claims.get("app_metadata", {})
    if isinstance(app_meta, dict) and app_meta.get("role"):
        return str(app_meta["role"])

    if claims.get("role"):
        return str(claims["role"])

    return "estudiante"


def _extract_role_from_db(conn: psycopg.Connection, user_id: str) -> str | None:
    """Consulta el rol del usuario desde la tabla `public.perfiles`.

    Args:
        conn: Conexión activa a PostgreSQL.
        user_id: UUID del usuario (claim `sub` del JWT).

    Returns:
        El rol ('admin', 'docente', 'estudiante') o None si no hay perfil.
    """
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT rol FROM public.perfiles WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        if row:
            return str(row["rol"])
    except Exception:
        # Si la tabla no existe o hay error de conexión, caemos al fallback
        pass
    return None


def _extract_role(
    claims: dict[str, Any],
    conn: psycopg.Connection | None = None,
) -> str:
    """Extrae el rol del usuario. Prioridad:

    1. Tabla `public.perfiles` (base de datos, fuente de verdad).
    2. Claims del JWT (fallback, para retrocompatibilidad).
    3. Default: "estudiante" (rol menos privilegiado).
    """
    user_id = claims.get("sub")
    if conn and user_id:
        db_role = _extract_role_from_db(conn, user_id)
        if db_role:
            return db_role

    return _extract_role_from_claims(claims)


def get_current_user_role(
    usuario: dict[str, Any] = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_db),
) -> str:
    """Dependencia que devuelve el rol del usuario autenticado.

    Consulta primero la tabla `public.perfiles` en la base de datos;
    si no hay registro, cae al fallback de los claims del JWT.
    """
    return _extract_role(usuario, conn)


def require_roles(allowed_roles: list[str]):
    """Dependencia de fábrica que valida el token y exige uno de los roles permitidos.

    Uso:
        @router.post("/generar", dependencies=[Depends(require_roles(["admin"]))])
        def generar(...):

    Lanza 403 si el usuario autenticado no tiene ninguno de los roles permitidos.
    """
    def _check_role(
        usuario: dict[str, Any] = Depends(get_current_user),
        conn: psycopg.Connection = Depends(get_db),
    ) -> dict[str, Any]:
        role = _extract_role(usuario, conn)
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: se requiere uno de los roles {allowed_roles}, tienes '{role}'.",
            )
        return usuario
    return _check_role
