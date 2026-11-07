"""Router CRUD de configuraciones de jornada (tabla `configs`).

Reglas institucionales:
  - Solo puede existir UNA configuración activa a la vez
    (índice parcial único `uidx_configs_activa`). Al crear o activar una
    configuración se desactiva la vigente en la misma transacción.
"""

import psycopg
from fastapi import APIRouter, Depends, status
from psycopg.rows import dict_row

from app.auth import get_current_user, require_roles
from app.db import get_db
from app.models.configs import ConfigCreate, ConfigUpdate, ConfigOut
from app.ownership import fetch_owned_record, owner_scope, request_role
from app.routers._common import build_update_statement, raise_db_error

router = APIRouter(
    prefix="/configs",
    tags=["Configuraciones"],
    dependencies=[Depends(get_current_user)],
)

TABLE = "configs"
MODULE_ROLES = ["admin", "docente"]


def _fetch_or_404(conn, config_id: int, role: str, user_id: str) -> dict:
    return fetch_owned_record(conn, TABLE, config_id, role, user_id, "Configuración")


@router.get("", response_model=list[ConfigOut], dependencies=[Depends(require_roles(MODULE_ROLES))])
def list_configs(
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> list[dict]:
    """Lista todas las configuraciones de jornada registradas."""
    role = request_role(usuario, conn)
    predicate, params = owner_scope(role, usuario["sub"])
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM {TABLE} WHERE {predicate} ORDER BY id", params)
        return [dict(r) for r in cur.fetchall()]


@router.get(
    "/activa",
    response_model=ConfigOut | None,
    dependencies=[Depends(require_roles(MODULE_ROLES))],
)
def get_active_config(
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict | None:
    """Devuelve la configuración actualmente activa, o None si no existe."""
    request_role(usuario, conn)
    predicate, params = "user_id = %s", (usuario["sub"],)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT * FROM {TABLE} WHERE activa = true AND ({predicate}) ORDER BY id",
            params,
        )
        row = cur.fetchone()
    return dict(row) if row else None


@router.get("/{config_id}", response_model=ConfigOut, dependencies=[Depends(require_roles(MODULE_ROLES))])
def get_config(
    config_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Devuelve una configuración por su id."""
    return _fetch_or_404(conn, config_id, request_role(usuario, conn), usuario["sub"])


@router.post("", response_model=ConfigOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(MODULE_ROLES))])
def create_config(
    payload: ConfigCreate,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Crea una configuración de jornada.

    Si se crea como `activa=true`, se desactiva la anterior dentro de la misma
    transacción para respetar `uidx_configs_activa`.
    """
    owner_id = usuario["sub"]
    try:
        with conn.transaction():
            if payload.activa:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE {TABLE} SET activa = false WHERE activa = true AND user_id = %s",
                        (owner_id,),
                    )
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    INSERT INTO {TABLE}
                        (nombre, tipo_jornada, dias_laborables, hora_inicio,
                         hora_fin, minutos_bloque, activa, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        payload.nombre,
                        payload.tipo_jornada,
                        payload.dias_laborables,
                        payload.hora_inicio,
                        payload.hora_fin,
                        payload.minutos_bloque,
                        payload.activa,
                        owner_id,
                    ),
                )
                row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.put("/{config_id}", response_model=ConfigOut, dependencies=[Depends(require_roles(MODULE_ROLES))])
def update_config(
    config_id: int,
    payload: ConfigUpdate,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Actualiza parcialmente una configuración.

    Si se activa, se desactivan las demás dentro de la misma transacción.
    """
    updates = payload.model_dump(exclude_unset=True)
    existing = _fetch_or_404(conn, config_id, request_role(usuario, conn), usuario["sub"])
    try:
        with conn.transaction():
            if updates.get("activa") is True:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE {TABLE} SET activa = false "
                        f"WHERE activa = true AND id <> %s AND user_id = %s",
                        (config_id, existing["user_id"]),
                    )
            sql, params = build_update_statement(TABLE, "id", config_id, updates)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(MODULE_ROLES))])
def delete_config(
    config_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> None:
    """Elimina una configuración (tiene `ON DELETE RESTRICT` desde horarios)."""
    _fetch_or_404(conn, config_id, request_role(usuario, conn), usuario["sub"])
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (config_id,))
    except psycopg.Error as exc:
        raise_db_error(exc)
