"""Router CRUD de salones y laboratorios (tabla `salones`)."""

import psycopg
from fastapi import APIRouter, Depends, status
from psycopg.rows import dict_row

from app.auth import get_current_user, require_roles
from app.db import get_db
from app.models.salones import SalonCreate, SalonUpdate, SalonOut
from app.ownership import fetch_owned_record, owner_scope, request_role
from app.routers._common import build_update_statement, raise_db_error

router = APIRouter(
    prefix="/salones",
    tags=["Salones"],
    dependencies=[Depends(get_current_user)],
)

TABLE = "salones"
MODULE_ROLES = ["admin", "docente"]


@router.get("", response_model=list[SalonOut], dependencies=[Depends(require_roles(MODULE_ROLES))])
def list_salones(
    activo: bool | None = None,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> list[dict]:
    """Lista salones; opcionalmente filtra por `activo`."""
    query = f"SELECT * FROM {TABLE}"
    predicate, owner_params = owner_scope(request_role(usuario, conn), usuario["sub"])
    query += f" WHERE {predicate}"
    params: list = list(owner_params)
    if activo is not None:
        query += " AND activo = %s"
        params.append(activo)
    query += " ORDER BY nombre"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


@router.get("/{salon_id}", response_model=SalonOut, dependencies=[Depends(require_roles(MODULE_ROLES))])
def get_salon(
    salon_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Devuelve un salón por su id."""
    return fetch_owned_record(conn, TABLE, salon_id, request_role(usuario, conn), usuario["sub"], "Salón")


@router.post("", response_model=SalonOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(MODULE_ROLES))])
def create_salon(
    payload: SalonCreate,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Crea un salón (nombre único)."""
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (nombre, tipo, capacidad, activo, user_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (payload.nombre, payload.tipo, payload.capacidad, payload.activo, usuario["sub"]),
            )
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.put("/{salon_id}", response_model=SalonOut, dependencies=[Depends(require_roles(MODULE_ROLES))])
def update_salon(
    salon_id: int,
    payload: SalonUpdate,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Actualiza parcialmente un salón."""
    updates = payload.model_dump(exclude_unset=True)
    get_salon(salon_id, conn, usuario)  # 404 temprano
    try:
        sql, params = build_update_statement(TABLE, "id", salon_id, updates)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/{salon_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(MODULE_ROLES))])
def delete_salon(
    salon_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> None:
    """Elimina un salón (cascada sobre celdas)."""
    get_salon(salon_id, conn, usuario)  # 404 temprano
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (salon_id,))
    except psycopg.Error as exc:
        raise_db_error(exc)
