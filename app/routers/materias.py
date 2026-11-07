"""Router CRUD de materias (tabla `materias`).

Incluye las políticas de espacio (§5.2) y de intensidad horaria (min/max).
"""

import psycopg
from fastapi import APIRouter, Depends, status
from psycopg.rows import dict_row

from app.auth import get_current_user, require_roles
from app.db import get_db
from app.models.materias import MateriaCreate, MateriaUpdate, MateriaOut
from app.ownership import fetch_owned_record, owner_scope, request_role
from app.routers._common import build_update_statement, raise_db_error

router = APIRouter(
    prefix="/materias",
    tags=["Materias"],
    dependencies=[Depends(get_current_user)],
)

TABLE = "materias"
MODULE_ROLES = ["admin", "docente"]


@router.get("", response_model=list[MateriaOut], dependencies=[Depends(require_roles(MODULE_ROLES))])
def list_materias(
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> list[dict]:
    """Lista todas las materias del plan de estudios.
    Si la tabla está vacía o hay error de BD, retorna [] con 200."""
    try:
        predicate, params = owner_scope(request_role(usuario, conn), usuario["sub"])
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT * FROM {TABLE} WHERE {predicate} ORDER BY nombre", params)
            return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        print(f"[ERROR list_materias] {exc}")
        return []


@router.get("/{materia_id}", response_model=MateriaOut, dependencies=[Depends(require_roles(MODULE_ROLES))])
def get_materia(
    materia_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Devuelve una materia por su id."""
    return fetch_owned_record(conn, TABLE, materia_id, request_role(usuario, conn), usuario["sub"], "Materia")


@router.post("", response_model=MateriaOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(MODULE_ROLES))])
def create_materia(
    payload: MateriaCreate,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Crea una materia (nombre único); valida la combinación requiere_salon/tipo."""
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE}
                    (nombre, categoria, min_horas, max_horas, requiere_salon,
                     tipo_salon_requerido, no_ultima_hora, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    payload.nombre,
                    payload.categoria,
                    payload.min_horas,
                    payload.max_horas,
                    payload.requiere_salon,
                    payload.tipo_salon_requerido,
                    payload.no_ultima_hora,
                    usuario["sub"],
                ),
            )
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.put("/{materia_id}", response_model=MateriaOut, dependencies=[Depends(require_roles(MODULE_ROLES))])
def update_materia(
    materia_id: int,
    payload: MateriaUpdate,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Actualiza parcialmente una materia."""
    updates = payload.model_dump(exclude_unset=True)
    get_materia(materia_id, conn, usuario)  # 404 temprano
    try:
        sql, params = build_update_statement(TABLE, "id", materia_id, updates)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/{materia_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(MODULE_ROLES))])
def delete_materia(
    materia_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> None:
    """Elimina una materia (cascada sobre asignaciones y celdas)."""
    get_materia(materia_id, conn, usuario)  # 404 temprano
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (materia_id,))
    except psycopg.Error as exc:
        raise_db_error(exc)
