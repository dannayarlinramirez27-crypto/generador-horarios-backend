"""Router CRUD de docentes y su disponibilidad horaria.

Endpoints:
  - CRUD de docentes (tabla `docentes`).
  - Sub-recurso `disponibilidades` (tabla `disponibilidades`):
    listar/crear/eliminar ventanas horarias de un docente.
"""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.auth import get_current_user, require_roles
from app.db import get_db
from app.models.docentes import DocenteCreate, DocenteUpdate, DocenteOut
from app.models.disponibilidades import (
    DisponibilidadCreate,
    DisponibilidadOut,
)
from app.routers._common import build_update_statement, raise_db_error

router = APIRouter(
    prefix="/docentes",
    tags=["Docentes"],
    dependencies=[Depends(get_current_user)],
)

ADMIN_ONLY = ["admin"]
READ_ROLES = ["admin", "docente", "estudiante"]

DOC_TABLE = "docentes"
DISP_TABLE = "disponibilidades"


def _get_docente(conn, docente_id: int) -> dict:
    """Devuelve el docente o eleva 404."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM {DOC_TABLE} WHERE id = %s", (docente_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Docente {docente_id} no encontrado.",
        )
    return dict(row)


# ---------------------------------------------------------------------------
# CRUD de docentes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[DocenteOut], dependencies=[Depends(require_roles(READ_ROLES))])
def list_docentes(
    activo: bool | None = None,
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista docentes; opcionalmente filtra por `activo`.
    Si la tabla está vacía o hay error de BD, retorna [] con 200."""
    try:
        query = f"SELECT * FROM {DOC_TABLE}"
        params: list = []
        if activo is not None:
            query += " WHERE activo = %s"
            params.append(activo)
        query += " ORDER BY apellido, nombre"
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        print(f"[ERROR list_docentes] {exc}")
        return []


@router.get("/{docente_id}", response_model=DocenteOut, dependencies=[Depends(require_roles(READ_ROLES))])
def get_docente(
    docente_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Devuelve un docente por su id."""
    return _get_docente(conn, docente_id)


@router.post("", response_model=DocenteOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def create_docente(
    payload: DocenteCreate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Registra un docente (documento y email únicos)."""
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                INSERT INTO {DOC_TABLE}
                    (nombre, apellido, documento, telefono, email,
                     carga_horaria, activo)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    payload.nombre,
                    payload.apellido,
                    payload.documento,
                    payload.telefono,
                    payload.email,
                    payload.carga_horaria,
                    payload.activo,
                ),
            )
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.put("/{docente_id}", response_model=DocenteOut)
def update_docente(
    docente_id: int,
    payload: DocenteUpdate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Actualiza parcialmente un docente."""
    updates = payload.model_dump(exclude_unset=True)
    _get_docente(conn, docente_id)
    try:
        sql, params = build_update_statement(DOC_TABLE, "id", docente_id, updates)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/{docente_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_docente(
    docente_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> None:
    """Elimina físicamente un docente (cascada sobre disponibilidades y asignaciones)."""
    _get_docente(conn, docente_id)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {DOC_TABLE} WHERE id = %s", (docente_id,))
    except psycopg.Error as exc:
        raise_db_error(exc)


# ---------------------------------------------------------------------------
# Disponibilidad horaria del docente
# ---------------------------------------------------------------------------


@router.get("/{docente_id}/disponibilidades", response_model=list[DisponibilidadOut])
def list_disponibilidades(
    docente_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista las ventanas horarias de un docente (404 si el docente no existe)."""
    _get_docente(conn, docente_id)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT * FROM {DISP_TABLE} WHERE docente_id = %s ORDER BY dia, hora_inicio",
            (docente_id,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.post(
    "/{docente_id}/disponibilidades",
    response_model=DisponibilidadOut,
    status_code=status.HTTP_201_CREATED,
)
def create_disponibilidad(
    docente_id: int,
    payload: DisponibilidadCreate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Agrega una ventana horaria al docente (Unique docente, día, hora inicio/fin)."""
    _get_docente(conn, docente_id)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                INSERT INTO {DISP_TABLE} (docente_id, dia, hora_inicio, hora_fin)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (docente_id, payload.dia, payload.hora_inicio, payload.hora_fin),
            )
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete(
    "/{docente_id}/disponibilidades/{disp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_disponibilidad(
    docente_id: int,
    disp_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> None:
    """Elimina una ventana horaria del docente."""
    _get_docente(conn, docente_id)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM disponibilidades WHERE id = %s AND docente_id = %s",
            (disp_id, docente_id),
        )
        if cur.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Disponibilidad {disp_id} no encontrada.",
            )
        cur.execute("DELETE FROM disponibilidades WHERE id = %s", (disp_id,))