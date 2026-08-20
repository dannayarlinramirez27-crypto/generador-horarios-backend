"""Router CRUD de materias (tabla `materias`).

Incluye las políticas de espacio (§5.2) y de intensidad horaria (min/max).
"""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.auth import get_current_user
from app.db import get_db
from app.models.materias import MateriaCreate, MateriaUpdate, MateriaOut
from app.routers._common import build_update_statement, raise_db_error

router = APIRouter(
    prefix="/materias",
    tags=["Materias"],
    dependencies=[Depends(get_current_user)],
)

TABLE = "materias"


@router.get("", response_model=list[MateriaOut])
def list_materias(
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista todas las materias del plan de estudios."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM {TABLE} ORDER BY nombre")
        return [dict(r) for r in cur.fetchall()]


@router.get("/{materia_id}", response_model=MateriaOut)
def get_materia(
    materia_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Devuelve una materia por su id."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM {TABLE} WHERE id = %s", (materia_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Materia {materia_id} no encontrada.",
        )
    return dict(row)


@router.post("", response_model=MateriaOut, status_code=status.HTTP_201_CREATED)
def create_materia(
    payload: MateriaCreate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Crea una materia (nombre único); valida la combinación requiere_salon/tipo."""
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE}
                    (nombre, categoria, min_horas, max_horas, requiere_salon,
                     tipo_salon_requerido, no_ultima_hora)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
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
                ),
            )
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.put("/{materia_id}", response_model=MateriaOut)
def update_materia(
    materia_id: int,
    payload: MateriaUpdate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Actualiza parcialmente una materia."""
    updates = payload.model_dump(exclude_unset=True)
    get_materia(materia_id, conn)  # 404 temprano
    try:
        sql, params = build_update_statement(TABLE, "id", materia_id, updates)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/{materia_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_materia(
    materia_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> None:
    """Elimina una materia (cascada sobre asignaciones y celdas)."""
    get_materia(materia_id, conn)  # 404 temprano
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (materia_id,))
    except psycopg.Error as exc:
        raise_db_error(exc)