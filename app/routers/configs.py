"""Router CRUD de configuraciones de jornada (tabla `configs`).

Reglas institucionales:
  - Solo puede existir UNA configuración activa a la vez
    (índice parcial único `uidx_configs_activa`). Al crear o activar una
    configuración se desactiva la vigente en la misma transacción.
"""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.db import get_db
from app.models.configs import ConfigCreate, ConfigUpdate, ConfigOut
from app.routers._common import build_update_statement, raise_db_error

router = APIRouter(prefix="/configs", tags=["Configuraciones"])

TABLE = "configs"


def _fetch_or_404(conn, config_id: int) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM {TABLE} WHERE id = %s", (config_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuración {config_id} no encontrada.",
        )
    return dict(row)


@router.get("", response_model=list[ConfigOut])
def list_configs(
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista todas las configuraciones de jornada registradas."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM {TABLE} ORDER BY id")
        return [dict(r) for r in cur.fetchall()]


@router.get("/activa", response_model=ConfigOut)
def get_active_config(
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Devuelve la configuración actualmente activa (404 si no existe)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM {TABLE} WHERE activa = true ORDER BY id")
        row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay ninguna configuración de jornada activa.",
        )
    return dict(row)


@router.get("/{config_id}", response_model=ConfigOut)
def get_config(
    config_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Devuelve una configuración por su id."""
    return _fetch_or_404(conn, config_id)


@router.post("", response_model=ConfigOut, status_code=status.HTTP_201_CREATED)
def create_config(
    payload: ConfigCreate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Crea una configuración de jornada.

    Si se crea como `activa=true`, se desactiva la anterior dentro de la misma
    transacción para respetar `uidx_configs_activa`.
    """
    try:
        with conn.transaction():
            if payload.activa:
                with conn.cursor() as cur:
                    cur.execute(f"UPDATE {TABLE} SET activa = false WHERE activa = true")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    INSERT INTO {TABLE}
                        (nombre, tipo_jornada, dias_laborables, hora_inicio,
                         hora_fin, minutos_bloque, activa)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
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
                    ),
                )
                row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.put("/{config_id}", response_model=ConfigOut)
def update_config(
    config_id: int,
    payload: ConfigUpdate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Actualiza parcialmente una configuración.

    Si se activa, se desactivan las demás dentro de la misma transacción.
    """
    updates = payload.model_dump(exclude_unset=True)
    _fetch_or_404(conn, config_id)  # 404 temprano
    try:
        with conn.transaction():
            if updates.get("activa") is True:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE {TABLE} SET activa = false "
                        f"WHERE activa = true AND id <> %s",
                        (config_id,),
                    )
            sql, params = build_update_statement(TABLE, "id", config_id, updates)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    config_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> None:
    """Elimina una configuración (tiene `ON DELETE RESTRICT` desde horarios)."""
    _fetch_or_404(conn, config_id)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (config_id,))
    except psycopg.Error as exc:
        raise_db_error(exc)