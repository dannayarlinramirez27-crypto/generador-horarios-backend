"""Router de asignaciones docente ↔ materia / docente ↔ curso.

Endpoints de catálogo (tablas `docente_materia` y `docente_curso`):
  - `docente_materia`: materias que un docente puede dictar (§5.1).
  - `docente_curso`  : cursos que le corresponden dar (§5.1).
Ambas con tabla intermedia + UNIQUE(docente, recurso).
"""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.db import get_db
from app.models.asignaciones import (
    DocenteMateriaCreate,
    DocenteMateriaOut,
    DocenteCursoCreate,
    DocenteCursoOut,
)
from app.routers._common import raise_db_error

router = APIRouter(prefix="/asignaciones", tags=["Asignaciones"])


def _docente_existe(conn, docente_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM docentes WHERE id = %s", (docente_id,))
        if cur.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Docente {docente_id} no encontrado.",
            )


# ---------------------------------------------------------------------------
# docente_materia — materias que cada docente puede dictar
# ---------------------------------------------------------------------------


@router.get("/materias", response_model=list[DocenteMateriaOut])
def list_docente_materias(
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista todas las asignaciones docente ↔ materia."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM docente_materia ORDER BY docente_id, materia_id")
        return [dict(r) for r in cur.fetchall()]


@router.get("/materias/{docente_id}", response_model=list[DocenteMateriaOut])
def list_materias_de_docente(
    docente_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista las materias que puede dictar un docente."""
    _docente_existe(conn, docente_id)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM docente_materia WHERE docente_id = %s ORDER BY materia_id",
            (docente_id,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.post(
    "/materias",
    response_model=DocenteMateriaOut,
    status_code=status.HTTP_201_CREATED,
)
def assign_materia_a_docente(
    payload: DocenteMateriaCreate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Asigna una materia a un docente (UNIQUE docente+materia)."""
    _docente_existe(conn, payload.docente_id)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO docente_materia (docente_id, materia_id)
                VALUES (%s, %s)
                RETURNING *
                """,
                (payload.docente_id, payload.materia_id),
            )
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/materias/{docente_id}/{materia_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_materia_de_docente(
    docente_id: int,
    materia_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> None:
    """Quita la materia que un docente dicta."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM docente_materia WHERE docente_id = %s AND materia_id = %s",
            (docente_id, materia_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La asignación no existe.",
            )


# ---------------------------------------------------------------------------
# docente_curso — cursos que corresponden a cada docente
# ---------------------------------------------------------------------------


@router.get("/cursos", response_model=list[DocenteCursoOut])
def list_docente_cursos(
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista todas las asignaciones docente ↔ curso."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM docente_curso ORDER BY docente_id, curso_id")
        return [dict(r) for r in cur.fetchall()]


@router.get("/cursos/{docente_id}", response_model=list[DocenteCursoOut])
def list_cursos_de_docente(
    docente_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista los cursos que le corresponden dar a un docente."""
    _docente_existe(conn, docente_id)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM docente_curso WHERE docente_id = %s ORDER BY curso_id",
            (docente_id,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.post(
    "/cursos",
    response_model=DocenteCursoOut,
    status_code=status.HTTP_201_CREATED,
)
def assign_curso_a_docente(
    payload: DocenteCursoCreate,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Asigna un curso a un docente (UNIQUE docente+curso)."""
    _docente_existe(conn, payload.docente_id)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO docente_curso (docente_id, curso_id)
                VALUES (%s, %s)
                RETURNING *
                """,
                (payload.docente_id, payload.curso_id),
            )
            row = cur.fetchone()
        return dict(row)
    except psycopg.Error as exc:
        raise_db_error(exc)


@router.delete("/cursos/{docente_id}/{curso_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_curso_de_docente(
    docente_id: int,
    curso_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> None:
    """Quita el curso que corresponde a un docente."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM docente_curso WHERE docente_id = %s AND curso_id = %s",
            (docente_id, curso_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La asignación no existe.",
            )