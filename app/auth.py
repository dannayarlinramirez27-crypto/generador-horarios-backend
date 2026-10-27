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
  - "admin": Acceso total.
  - "docente": Puede gestionar los módulos habilitados y sus propios horarios.
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

ROLES_VALIDOS = {"admin", "docente"}
ROL_DESCONOCIDO = "desconocido"

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
    """Extrae un rol válido de los claims de Supabase gestionados por el servidor.

    NUNCA lee el claim `role` de nivel superior porque Supabase siempre
    lo envía como "authenticated" (rol interno de Auth, no nuestro RBAC).

    `app_metadata` solo puede ser escrito por código de confianza. `user_metadata`
    es editable por el usuario y no concede ningún rol por sí solo.
    """
    app_meta = claims.get("app_metadata", {})
    role = app_meta.get("role") if isinstance(app_meta, dict) else None
    if isinstance(role, str) and role in ROLES_VALIDOS:
        return role

    return ROL_DESCONOCIDO


def _extract_docente_from_db(conn: psycopg.Connection, email: str) -> str | None:
    """Resuelve docente solo cuando existe un único registro con ese email.

    Args:
        conn: Conexión activa a PostgreSQL.
        email: Email del JWT ya verificado.

    Returns:
        `docente` si hay exactamente una coincidencia; de lo contrario, None.
    """
    if not isinstance(email, str) or not email.strip():
        return None

    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT email FROM public.docentes WHERE lower(email) = lower(%s)",
                (email.strip(),),
            )
            rows = cur.fetchall()
        if len(rows) == 1:
            return "docente"
    except Exception:
        pass
    return None


def _extract_role(
    claims: dict[str, Any],
    conn: psycopg.Connection | None = None,
) -> str:
    """Resuelve un rol a partir de claims confiables y tablas existentes.

    Los roles válidos de `app_metadata` son claims administrados por el servidor.
    El email de compatibilidad concede admin únicamente a las cuentas históricas
    de confianza. Para docente se exige una coincidencia única en `docentes.email`;
    `user_metadata.role` puede expresar intención de registro, pero no autoriza.
    """
    claim_role = _extract_role_from_claims(claims)
    if claim_role != ROL_DESCONOCIDO:
        return claim_role

    email = claims.get("email", "")
    if isinstance(email, str) and email.strip().lower() in {
        "dannayarlinramirez0827@gmail.com",
        "dannayarlinramirez27@gmail.com",
    }:
        return "admin"

    if conn:
        db_role = _extract_docente_from_db(conn, email)
        if db_role:
            return db_role

    return ROL_DESCONOCIDO


def ensure_role_allowed(role: str, allowed_roles: list[str]) -> None:
    """Lanza 403 cuando el rol resuelto no pertenece a la lista permitida."""
    if role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado: se requiere uno de los roles {allowed_roles}, tienes '{role}'.",
        )


def get_current_user_role(
    usuario: dict[str, Any] = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_db),
) -> str:
    """Dependencia que devuelve el rol resuelto para el usuario autenticado."""
    return _extract_role(usuario, conn)


def require_roles(allowed_roles: list[str]):
    """Dependencia de fábrica que valida el token y exige uno de los roles permitidos.

    Uso:
        @router.post("/generar", dependencies=[Depends(require_roles(["admin", "docente"]))])
        def generar(...):

    Lanza 403 si el usuario autenticado no tiene ninguno de los roles permitidos.
    """
    def _check_role(
        usuario: dict[str, Any] = Depends(get_current_user),
        conn: psycopg.Connection = Depends(get_db),
    ) -> dict[str, Any]:
        role = _extract_role(usuario, conn)
        ensure_role_allowed(role, allowed_roles)
        return usuario
    return _check_role
