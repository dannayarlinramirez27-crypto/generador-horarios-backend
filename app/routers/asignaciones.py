"""Router de asignaciones docente ↔ materia / docente ↔ curso.

Endpoints de catálogo (tablas `docente_materia` y `docente_curso`):
  - `docente_materia`: materias que un docente puede dictar (§5.1).
  - `docente_curso`  : cursos que le corresponden dar (§5.1).
Ambas con tabla intermedia + UNIQUE(docente, recurso).
"""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.auth import get_current_user, require_roles
from app.db import get_db
from app.models.asignaciones import (
    DocenteMateriaCreate,
    DocenteMateriaOut,
    DocenteCursoCreate,
    DocenteCursoOut,
)
from app.ownership import fetch_owned_record, owner_scope, referenced_owner, request_role


router = APIRouter(
    prefix="/asignaciones",
    tags=["Asignaciones"],
    dependencies=[Depends(get_current_user)],
)
MODULE_ROLES = ["admin", "docente"]


def _docente_existe(conn, docente_id: int, role: str, user_id: str) -> dict:
    return fetch_owned_record(conn, "docentes", docente_id, role, user_id, "Docente")


# ---------------------------------------------------------------------------
# docente_materia — materias que cada docente puede dictar
# ---------------------------------------------------------------------------


@router.get("/materias", response_model=list[DocenteMateriaOut], dependencies=[Depends(require_roles(MODULE_ROLES))])
def list_docente_materias(
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> list[dict]:
    """Lista todas las asignaciones docente ↔ materia."""
    predicate, params = owner_scope(request_role(usuario, conn), usuario["sub"])
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM docente_materia WHERE {predicate} ORDER BY docente_id, materia_id", params)
        return [dict(r) for r in cur.fetchall()]


@router.get("/materias/{docente_id}", response_model=list[DocenteMateriaOut], dependencies=[Depends(require_roles(MODULE_ROLES))])
def list_materias_de_docente(
    docente_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> list[dict]:
    """Lista las materias que puede dictar un docente."""
    try:
        role = request_role(usuario, conn)
        docente = _docente_existe(conn, docente_id, role, usuario["sub"])
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM docente_materia WHERE docente_id = %s AND user_id = %s ORDER BY materia_id",
                (docente_id, docente["user_id"]),
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
    dependencies=[Depends(require_roles(MODULE_ROLES))],
)
def assign_materia_a_docente(
    payload: DocenteMateriaCreate,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Asigna una materia a un docente (UNIQUE docente+materia)."""
    role = request_role(usuario, conn)
    docente = _docente_existe(conn, payload.docente_id, role, usuario["sub"])
    referenced_owner(
        conn, "materias", payload.materia_id, role=role, actor_id=usuario["sub"],
        expected_owner_id=docente["user_id"], label="Materia",
    )
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO docente_materia (docente_id, materia_id, user_id)
                VALUES (%s, %s, %s)
                RETURNING *
                """,
                (payload.docente_id, payload.materia_id, docente["user_id"]),
            )
            row = cur.fetchone()
        return dict(row)
    except Exception as exc:
        print(f"[ERROR assign_materia] docente_id={payload.docente_id}, materia_id={payload.materia_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al asignar materia: {exc}",
        ) from exc


@router.delete("/materias/{docente_id}/{materia_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(MODULE_ROLES))])
def unassign_materia_de_docente(
    docente_id: int,
    materia_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> None:
    """Quita la materia que un docente dicta."""
    docente = _docente_existe(conn, docente_id, request_role(usuario, conn), usuario["sub"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM docente_materia WHERE docente_id = %s AND materia_id = %s AND user_id = %s",
                (docente_id, materia_id, docente["user_id"]),
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


@router.get("/cursos", response_model=list[DocenteCursoOut], dependencies=[Depends(require_roles(MODULE_ROLES))])
def list_docente_cursos(
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> list[dict]:
    """Lista todas las asignaciones docente ↔ curso."""
    predicate, params = owner_scope(request_role(usuario, conn), usuario["sub"])
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT * FROM docente_curso WHERE {predicate} ORDER BY docente_id, curso_id", params)
        return [dict(r) for r in cur.fetchall()]


@router.get("/cursos/{docente_id}", response_model=list[DocenteCursoOut], dependencies=[Depends(require_roles(MODULE_ROLES))])
def list_cursos_de_docente(
    docente_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> list[dict]:
    """Lista los cursos que le corresponden dar a un docente."""
    try:
        role = request_role(usuario, conn)
        docente = _docente_existe(conn, docente_id, role, usuario["sub"])
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM docente_curso WHERE docente_id = %s AND user_id = %s ORDER BY curso_id",
                (docente_id, docente["user_id"]),
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
    dependencies=[Depends(require_roles(MODULE_ROLES))],
)
def assign_curso_a_docente(
    payload: DocenteCursoCreate,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Asigna un curso a un docente (UNIQUE docente+curso)."""
    role = request_role(usuario, conn)
    docente = _docente_existe(conn, payload.docente_id, role, usuario["sub"])
    referenced_owner(
        conn, "cursos", payload.curso_id, role=role, actor_id=usuario["sub"],
        expected_owner_id=docente["user_id"], label="Curso",
    )
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO docente_curso (docente_id, curso_id, user_id)
                VALUES (%s, %s, %s)
                RETURNING *
                """,
                (payload.docente_id, payload.curso_id, docente["user_id"]),
            )
            row = cur.fetchone()
        return dict(row)
    except Exception as exc:
        print(f"[ERROR assign_curso] docente_id={payload.docente_id}, curso_id={payload.curso_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al asignar curso: {exc}",
        ) from exc


@router.delete("/cursos/{docente_id}/{curso_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(MODULE_ROLES))])
def unassign_curso_de_docente(
    docente_id: int,
    curso_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> None:
    """Quita el curso que corresponde a un docente."""
    docente = _docente_existe(conn, docente_id, request_role(usuario, conn), usuario["sub"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM docente_curso WHERE docente_id = %s AND curso_id = %s AND user_id = %s",
                (docente_id, curso_id, docente["user_id"]),
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
