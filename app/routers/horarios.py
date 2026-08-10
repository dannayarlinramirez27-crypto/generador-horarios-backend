"""Router de generación, consulta, edición y validación de horarios.

Endpoints (PLAN §7):
  · POST  /horarios/generar      (T-021) ejecuta el motor CSP y persiste.
  · GET   /horarios              (T-024) lista horarios guardados.
  · GET   /horarios/{id}         (T-024) devuelve horario + sus celdas.
  · POST  /horarios/{id}/editar  (T-023) mueve/agrega una celda validando en vivo.
  · POST  /horarios/validar      (T-022) verifica restricciones de un horario.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.db import get_db
from app.models.celdas import CeldaOut
from app.models.horarios import HorarioOut
from app.scheduler import load_problem, solve, validate_cell_move, validate_schedule

router = APIRouter(prefix="/horarios", tags=["Horarios"])


# ---------------------------------------------------------------------------
# Persistencia (transacción única por operación)
# ---------------------------------------------------------------------------


def _insert_horario(
    conn: psycopg.Connection,
    configuracion_id: int,
    nombre: str,
    estado: str,
) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO horarios (configuracion_id, nombre, estado)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (configuracion_id, nombre, estado),
        )
        row = cur.fetchone()
    return dict(row)


def _insert_celdas(
    conn: psycopg.Connection, horario_id: int, celdas: list[dict]
) -> list[dict]:
    """Inserta las celdas generadas y devuelve las filas completas."""
    filas: list[dict] = []
    with conn.cursor(row_factory=dict_row) as cur:
        for c in celdas:
            cur.execute(
                """
                INSERT INTO celdas
                    (horario_id, curso_id, materia_id, docente_id, salon_id,
                     dia, bloque, hora_inicio, hora_fin, bloqueada)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    horario_id,
                    c["curso_id"],
                    c["materia_id"],
                    c["docente_id"],
                    c["salon_id"],
                    c["dia"],
                    c["bloque"],
                    c["hora_inicio"],
                    c["hora_fin"],
                    c.get("bloqueada", False),
                ),
            )
            filas.append(dict(cur.fetchone()))
    return filas


def _load_horario(conn: psycopg.Connection, horario_id: int) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM horarios WHERE id = %s", (horario_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Horario {horario_id} no encontrado.",
        )
    return dict(row)


def _load_celdas_de(conn: psycopg.Connection, horario_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM celdas WHERE horario_id = %s ORDER BY dia, bloque, id",
            (horario_id,),
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# T-021 · Generar horario con el motor CSP
# ---------------------------------------------------------------------------


@router.post("/generar", status_code=status.HTTP_201_CREATED)
def generar(
    payload: dict,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Ejecuta el motor CSP y persiste horario + celdas en una transacción.

    Body opcional:
      · `nombre` → etiqueta del horario (por defecto "Horario").
      · `horario_id` → si se pasa, regenera SOBRE un horario existente
        conservando sus celdas `bloqueada = true` (inmutables) y respetando su
        configuración; en caso contrario usa la configuración activa.
    """
    nombre = str(payload.get("nombre", "Horario"))
    horario_id = payload.get("horario_id")

    problem, error = load_problem(conn, horario_id)
    if error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error["detail"])

    if not problem.cursos or not problem.materias or not problem.docentes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Faltan datos para generar: carga cursos, materias, docentes y salones.",
        )

    resultado = solve(problem)

    try:
        with conn.transaction():
            if horario_id is not None:
                # Regeneración: conservamos el id y refrescamos estado/etiqueta.
                _load_horario(conn, horario_id)
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM celdas WHERE horario_id = %s",
                        (horario_id,),
                    )
                    cur.execute(
                        "UPDATE horarios SET nombre = %s, estado = %s WHERE id = %s",
                        (nombre, resultado.estado, horario_id),
                    )
                horario = _load_horario(conn, horario_id)
                horario["estado"] = resultado.estado
            else:
                config_id = problem.jornada.config_id
                horario = _insert_horario(conn, config_id, nombre, resultado.estado)
                horario_id = horario["id"]

            celdas = _insert_celdas(conn, horario_id, resultado.celdas) if resultado.celdas else []
    except psycopg.Error as exc:
        # Los triggers del esquema (sch_celda_validar, sch_horario_validar)
        # también validan; si el solver generó algo inválido, se ve aquí.
        detail = getattr(exc, "diag", None)
        msg = str(exc).strip()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El guardado fue rechazado por la base de datos: {msg}",
        ) from exc

    return {
        "horario": horario,
        "estado": resultado.estado,
        "completo": resultado.completo,
        "celdas": celdas,
        "conflictos": resultado.conflictos,
        "avisos": resultado.avisos,
        "statistics": resultado.statistics,
    }


# ---------------------------------------------------------------------------
# T-024 · Consulta de horarios
# ---------------------------------------------------------------------------


@router.get("", response_model=list[HorarioOut])
def list_horarios(
    conn: psycopg.Connection = Depends(get_db),
) -> list[dict]:
    """Lista los horarios guardados (más recientes primero)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM horarios ORDER BY id DESC")
        return [dict(r) for r in cur.fetchall()]


@router.get("/{horario_id}")
def get_horario(
    horario_id: int,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Devuelve un horario con todas sus celdas."""
    horario = _load_horario(conn, horario_id)
    celdas = _load_celdas_de(conn, horario_id)
    return {"horario": horario, "celdas": celdas}


# ---------------------------------------------------------------------------
# T-022 · Validación de restricciones de un horario guardado
# ---------------------------------------------------------------------------


@router.post("/validar")
def validar_horario(
    payload: dict,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Verifica todas las restricciones de un horario y las reporta.

    Body: `{"horario_id": <id>}`. Devuelve `violaciones` (cada una con tipo y
    mensaje). Si la lista está vacía → horario válido.
    """
    horario_id = payload.get("horario_id")
    _load_horario(conn, horario_id)
    celdas = _load_celdas_de(conn, horario_id)

    problem, error = load_problem(conn, horario_id)
    if error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error["detail"])

    violaciones = validate_schedule(problem, celdas)
    return {
        "horario_id": horario_id,
        "valido": len(violaciones) == 0,
        "violaciones": violaciones,
    }


# ---------------------------------------------------------------------------
# T-023 · Editar / mover una celda con validación en vivo
# ---------------------------------------------------------------------------

_PARAMETROS_MOVIMIENTO = (
    "materia_id",
    "docente_id",
    "salon_id",
    "dia",
    "bloque",
    "hora_inicio",
    "hora_fin",
)


@router.post("/{horario_id}/editar")
def editar_celda(
    horario_id: int,
    payload: dict,
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Agrega o mueve una celda validando en tiempo real.

    Body:
      · `celda_id` (opcional) → si se pasa, es un MOVIMIENTO de esa celda
        (los campos no enviados conservan su valor actual).
      · Ningún `celda_id` → se crea una celda nueva con los campos dados.
      · `curso_id` es obligatorio y no cambia en un movimiento.

    La validación simula la celda final contra el resto; si hay violaciones de
    choque/disponibilidad/salón/jornada se responde 409 sin guardar nada.
    """
    celda_id = payload.get("celda_id")
    curso_id = payload.get("curso_id")
    if not curso_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`curso_id` es obligatorio.",
        )

    celdas_actuales = _load_celdas_de(conn, horario_id)

    # Construcción de la celda propuesta (nueva o resultado del movimiento).
    if celda_id is not None:
        anterior = next((c for c in celdas_actuales if c["id"] == celda_id), None)
        if anterior is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Celda {celda_id} no encontrada en el horario {horario_id}.",
            )
        propuesta = dict(anterior)
        propuesta.update({k: v for k, v in payload.items() if k in _PARAMETROS_MOVIMIENTO and v is not None})
        otras = [c for c in celdas_actuales if c["id"] != celda_id]
    else:
        propuesta = {
            "curso_id": curso_id,
            "materia_id": payload.get("materia_id"),
            "docente_id": payload.get("docente_id"),
            "salon_id": payload.get("salon_id"),
            "dia": payload.get("dia"),
            "bloque": payload.get("bloque"),
            "hora_inicio": payload.get("hora_inicio"),
            "hora_fin": payload.get("hora_fin"),
            "bloqueada": payload.get("bloqueada", False),
        }
        for k in _PARAMETROS_MOVIMIENTO:
            if propuesta.get(k) is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Falta el campo `{k}` en la nueva celda.",
                )
        otras = [c for c in celdas_actuales]

    # 1) Validación en vivo (sin tocar la BD).
    problem, error = load_problem(conn, horario_id)
    if error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error["detail"])

    violaciones = validate_cell_move(problem, otras, propuesta)
    violaciones_reales = [v for v in violaciones if v["tipo"] not in ("carga_curso_incompleta",)]

    if violaciones_reales:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "mensaje": "La celda viola restricciones del horario.",
                "violaciones": violaciones_reales,
            },
        )

    # 2) Persistencia.
    try:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                if celda_id is not None:
                    cur.execute(
                        """
                        UPDATE celdas
                           SET materia_id=%s, docente_id=%s, salon_id=%s,
                               dia=%s, bloque=%s, hora_inicio=%s, hora_fin=%s,
                               bloqueada=%s
                         WHERE id = %s AND horario_id = %s
                        RETURNING *
                        """,
                        (
                            propuesta["materia_id"],
                            propuesta["docente_id"],
                            propuesta["salon_id"],
                            propuesta["dia"],
                            propuesta["bloque"],
                            propuesta["hora_inicio"],
                            propuesta["hora_fin"],
                            propuesta.get("bloqueada", False),
                            celda_id,
                            horario_id,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO celdas
                            (horario_id, curso_id, materia_id, docente_id, salon_id,
                             dia, bloque, hora_inicio, hora_fin, bloqueada)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            horario_id,
                            curso_id,
                            propuesta["materia_id"],
                            propuesta["docente_id"],
                            propuesta["salon_id"],
                            propuesta["dia"],
                            propuesta["bloque"],
                            propuesta["hora_inicio"],
                            propuesta["hora_fin"],
                            propuesta.get("bloqueada", False),
                        ),
                    )
                fila = cur.fetchone()
    except psycopg.Error as exc:
        # Los triggers de la BD pueden rechazar lo que la validación local
        # aprobó (p. ej. carga académica acumulada en minutos exactos).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La base de datos rechazó la celda: {str(exc).strip()}",
        ) from exc

    advertencias = [v for v in violaciones if v["tipo"] == "carga_curso_incompleta"]
    return {
        "valido": True,
        "celda": dict(fila),
        "advertencias": advertencias,
    }