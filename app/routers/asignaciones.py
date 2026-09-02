"""Router de asignaciones docente ↔ materia / docente ↔ curso.

Endpoints de catálogo (tablas `docente_materia` y `docente_curso`):
  - `docente_materia`: materias que un docente puede dictar (§5.1).
  - `docente_curso`  : cursos que le corresponden dar (§5.1).
Ambas con tabla intermedia + UNIQUE(docente, recurso).
"""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.auth import get_current_user
from app.db import get_db
from app.models.asignaciones import (
    DocenteMateriaCreate,
    DocenteMateriaOut,
    DocenteCursoCreate,
    DocenteCursoOut,
)


router = APIRouter(
    prefix="/asignaciones",
    tags=["Asignaciones"],
    dependencies=[Depends(get_current_user)],
)


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
    try:
        _docente_existe(conn, docente_id)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM docente_materia WHERE docente_id = %s ORDER BY materia_id",
                (docente_id,),
            )
            return [dict(r) for r in cur.fetchall()]
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[ERROR list_materias_de_docente] docente_id={docente_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al listar materias del docente: {exc}",
        ) from exc


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
    except Exception as exc:
        print(f"[ERROR assign_materia] docente_id={payload.docente_id}, materia_id={payload.materia_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al asignar materia: {exc}",
        ) from exc


@router.delete("/materias/{docente_id}/{materia_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_materia_de_docente(
    docente_id: int,
    materia_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> None:
    """Quita la materia que un docente dicta."""
    try:
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
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[ERROR unassign_materia] docente_id={docente_id}, materia_id={materia_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al quitar materia: {exc}",
        ) from exc


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
    try:
        _docente_existe(conn, docente_id)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM docente_curso WHERE docente_id = %s ORDER BY curso_id",
                (docente_id,),
            )
            return [dict(r) for r in cur.fetchall()]
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[ERROR list_cursos_de_docente] docente_id={docente_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al listar cursos del docente: {exc}",
        ) from exc


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
    except Exception as exc:
        print(f"[ERROR assign_curso] docente_id={payload.docente_id}, curso_id={payload.curso_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al asignar curso: {exc}",
        ) from exc


@router.delete("/cursos/{docente_id}/{curso_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_curso_de_docente(
    docente_id: int,
    curso_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> None:
    """Quita el curso que corresponde a un docente."""
    try:
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
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[ERROR unassign_curso] docente_id={docente_id}, curso_id={curso_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al quitar curso: {exc}",
        ) from exc