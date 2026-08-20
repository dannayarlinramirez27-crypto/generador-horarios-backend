"""Router CRUD de salones y laboratorios (tabla `salones`)."""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.auth import get_current_user
from app.db import get_db
from app.models.salones import SalonCreate, SalonUpdate, SalonOut
from app.routers._common import build_update_statement, raise_db_error

router = APIRouter(
    prefix="/salones",
    tags=["Salones"],
    dependencies=[Depends(get_current_user)],
)

TABLE = "salones"


@router.get("", response_model=list[SalonOut])
def list_salones(
    activo: bool | None = None,
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista salones; opcionalmente filtra por `activo`."""
    query = f"SELECT * FROM {TABLE}"
    params: list = []
    if activo is not None:
        query += " WHERE activo = %s"
        params.append(activo)
    query += " ORDER BY nombre"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


@router.get("/{salon_id}", response_model=SalonOut)
def get_salon(
    salon_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Devuelve un salón por su id."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM {TABLE} WHERE id = %s", (salon_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Salón {salon_id} no encontrado.",
        )
    return dict(row)


@router.post("", response_model=SalonOut, status_code=status.HTTP_201_CREATED)
def create_salon(
    payload: SalonCreate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Crea un salón (nombre único)."""
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (nombre, tipo, capacidad, activo)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (payload.nombre, payload.tipo, payload.capacidad, payload.activo),
            )
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.put("/{salon_id}", response_model=SalonOut)
def update_salon(
    salon_id: int,
    payload: SalonUpdate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Actualiza parcialmente un salón."""
    updates = payload.model_dump(exclude_unset=True)
    get_salon(salon_id, conn)  # 404 temprano
    try:
        sql, params = build_update_statement(TABLE, "id", salon_id, updates)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/{salon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_salon(
    salon_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> None:
    """Elimina un salón (cascada sobre celdas)."""
    get_salon(salon_id, conn)  # 404 temprano
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (salon_id,))
    except psycopg.Error as exc:
        raise_db_error(exc)