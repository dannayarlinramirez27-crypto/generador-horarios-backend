"""Router CRUD de cursos/grados (tabla `cursos`)."""

import psycopg
from fastapi import APIRouter, Depends, status
from psycopg.rows import dict_row

from app.auth import get_current_user, require_roles
from app.db import get_db
from app.models.cursos import CursoCreate, CursoUpdate, CursoOut
from app.ownership import fetch_owned_record, owner_scope, request_role
from app.routers._common import build_update_statement, raise_db_error

router = APIRouter(
    prefix="/cursos",
    tags=["Cursos"],
    dependencies=[Depends(get_current_user)],
)

TABLE = "cursos"
MODULE_ROLES = ["admin", "docente"]


@router.get("", response_model=list[CursoOut], dependencies=[Depends(require_roles(MODULE_ROLES))])
def list_cursos(
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> list[dict]:
    """Lista todos los cursos ordenados por nivel/orden.
    Si la tabla está vacía o hay error de BD, retorna [] con 200."""
    try:
        predicate, params = owner_scope(request_role(usuario, conn), usuario["sub"])
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT * FROM {TABLE} WHERE {predicate} ORDER BY orden, nombre", params)
            return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        print(f"[ERROR list_cursos] {exc}")
        return []


@router.get("/{curso_id}", response_model=CursoOut, dependencies=[Depends(require_roles(MODULE_ROLES))])
def get_curso(
    curso_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Devuelve un curso por su id."""
    return fetch_owned_record(conn, TABLE, curso_id, request_role(usuario, conn), usuario["sub"], "Curso")


@router.post("", response_model=CursoOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(MODULE_ROLES))])
def create_curso(
    payload: CursoCreate,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Crea un curso (nombre único)."""
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (nombre, nivel, horas_semanales, orden, user_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (payload.nombre, payload.nivel, payload.horas_semanales, payload.orden, usuario["sub"]),
            )
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.put("/{curso_id}", response_model=CursoOut, dependencies=[Depends(require_roles(MODULE_ROLES))])
def update_curso(
    curso_id: int,
    payload: CursoUpdate,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Actualiza parcialmente un curso."""
    updates = payload.model_dump(exclude_unset=True)
    get_curso(curso_id, conn, usuario)  # 404 temprano
    try:
        sql, params = build_update_statement(TABLE, "id", curso_id, updates)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/{curso_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(MODULE_ROLES))])
def delete_curso(
    curso_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> None:
    """Elimina un curso (cascada sobre celdas y asignaciones)."""
    get_curso(curso_id, conn, usuario)  # 404 temprano
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (curso_id,))
    except psycopg.Error as exc:
        raise_db_error(exc)
