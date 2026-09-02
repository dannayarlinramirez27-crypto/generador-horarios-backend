"""Router CRUD de cursos/grados (tabla `cursos`)."""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.auth import get_current_user
from app.db import get_db
from app.models.cursos import CursoCreate, CursoUpdate, CursoOut
from app.routers._common import build_update_statement, raise_db_error

router = APIRouter(
    prefix="/cursos",
    tags=["Cursos"],
    dependencies=[Depends(get_current_user)],
)

TABLE = "cursos"


@router.get("", response_model=list[CursoOut])
def list_cursos(
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista todos los cursos ordenados por nivel/orden.
    Si la tabla está vacía o hay error de BD, retorna [] con 200."""
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT * FROM {TABLE} ORDER BY orden, nombre")
            return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        print(f"[ERROR list_cursos] {exc}")
        return []


@router.get("/{curso_id}", response_model=CursoOut)
def get_curso(
    curso_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Devuelve un curso por su id."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM {TABLE} WHERE id = %s", (curso_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Curso {curso_id} no encontrado.",
        )
    return dict(row)


@router.post("", response_model=CursoOut, status_code=status.HTTP_201_CREATED)
def create_curso(
    payload: CursoCreate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Crea un curso (nombre único)."""
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (nombre, nivel, horas_semanales, orden)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (payload.nombre, payload.nivel, payload.horas_semanales, payload.orden),
            )
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.put("/{curso_id}", response_model=CursoOut)
def update_curso(
    curso_id: int,
    payload: CursoUpdate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Actualiza parcialmente un curso."""
    updates = payload.model_dump(exclude_unset=True)
    get_curso(curso_id, conn)  # 404 temprano
    try:
        sql, params = build_update_statement(TABLE, "id", curso_id, updates)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/{curso_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_curso(
    curso_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> None:
    """Elimina un curso (cascada sobre celdas y asignaciones)."""
    get_curso(curso_id, conn)  # 404 temprano
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (curso_id,))
    except psycopg.Error as exc:
        raise_db_error(exc)