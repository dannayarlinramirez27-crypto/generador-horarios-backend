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
  - "docente": Gestiona materias, su disponibilidad y genera horarios.
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
    """Extrae un rol válido de los claims de Supabase.

    NUNCA lee el claim `role` de nivel superior porque Supabase siempre
    lo envía como "authenticated" (rol interno de Auth, no nuestro RBAC).

    `app_metadata` solo puede ser escrito por código de confianza. El flujo
    existente de registro sí permite solicitar el rol docente mediante
    `user_metadata`; ese dato nunca puede conceder el rol admin.
    """
    app_meta = claims.get("app_metadata", {})
    role = app_meta.get("role") if isinstance(app_meta, dict) else None
    if isinstance(role, str) and role in ROLES_VALIDOS:
        return str(role)

    user_meta = claims.get("user_metadata", {})
    signup_role = user_meta.get("role") if isinstance(user_meta, dict) else None
    if signup_role == "docente":
        return "docente"

    return ROL_DESCONOCIDO


def _extract_role_from_db(conn: psycopg.Connection, user_id: str) -> str | None:
    """Consulta el rol del usuario desde la tabla `public.perfiles`.

    Args:
        conn: Conexión activa a PostgreSQL.
        user_id: UUID del usuario (claim `sub` del JWT).

    Returns:
        El rol ('admin' o 'docente') o None si no hay perfil válido.
    """
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT rol FROM public.perfiles WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        if row:
            role = row.get("rol")
            if isinstance(role, str) and role in ROLES_VALIDOS:
                return role
    except Exception:
        pass
    return None


def _extract_role(
    claims: dict[str, Any],
    conn: psycopg.Connection | None = None,
) -> str:
    """Extrae el rol del usuario. Prioridad:

    1. Tabla `public.perfiles` (base de datos, fuente de verdad).
    2. `app_metadata` del JWT (claims gestionados por el servidor).
    3. `user_metadata.role == "docente"` (compatibilidad con el registro actual).
    4. Fallback admin de email, conservado para la cuenta de confianza existente.
    5. Rol interno no autorizado cuando no hay una asignación válida.
    """
    user_id = claims.get("sub")
    if conn and user_id:
        db_role = _extract_role_from_db(conn, user_id)
        if db_role:
            return db_role

    claim_role = _extract_role_from_claims(claims)
    if claim_role != ROL_DESCONOCIDO:
        return claim_role

    email = claims.get("email", "")
    if email in ("dannayarlinramirez0827@gmail.com", "dannayarlinramirez27@gmail.com"):
        return "admin"

    return ROL_DESCONOCIDO


def _extract_docente_id_from_email(
    conn: psycopg.Connection, email: str | None
) -> int | None:
    """Resuelve un registro docente mediante el email verificado del JWT.

    Si el email es nulo, no hay coincidencia o hay más de una coincidencia
    ignorando mayúsculas, se falla de forma cerrada.
    """
    if not email:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM docentes WHERE LOWER(email) = LOWER(%s)",
                (email,),
            )
            rows = cur.fetchall()
        if len(rows) != 1:
            return None
        row = rows[0]
        return int(row["id"] if isinstance(row, dict) else row[0])
    except Exception:
        return None


def ensure_role_allowed(role: str, allowed_roles: list[str]) -> None:
    """Lanza 403 cuando el rol resuelto no pertenece a la lista permitida."""
    if role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado: se requiere uno de los roles {allowed_roles}, tienes '{role}'.",
        )


def ensure_docente_access(
    role: str, requested_docente_id: int, linked_docente_id: int | None
) -> None:
    """Permite a admin cualquier registro y a docentes solo su propio registro."""
    if role == "admin":
        return
    if role != "docente":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: solo admin y docente pueden gestionar disponibilidades.",
        )
    if linked_docente_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta docente no está vinculada a un registro por email. Contacta con un administrador.",
        )
    if requested_docente_id != linked_docente_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes gestionar tu propia disponibilidad docente.",
        )


def require_docente_access():
    """Dependencia de autorización para disponibilidad docente propia o admin."""
    def _check_docente_access(
        docente_id: int,
        usuario: dict[str, Any] = Depends(get_current_user),
        conn: psycopg.Connection = Depends(get_db),
    ) -> None:
        role = _extract_role(usuario, conn)
        linked_id = (
            _extract_docente_id_from_email(conn, usuario.get("email"))
            if role == "docente"
            else None
        )
        ensure_docente_access(role, docente_id, linked_id)

    return _check_docente_access


def get_current_user_role(
    usuario: dict[str, Any] = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_db),
) -> str:
    """Dependencia que devuelve el rol del usuario autenticado.

    Consulta primero la tabla `public.perfiles` en la base de datos;
    si no hay registro, cae a `app_metadata` gestionado por el servidor.
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
        ensure_role_allowed(role, allowed_roles)
        return usuario
    return _check_role
