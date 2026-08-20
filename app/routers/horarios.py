"""Router de generación, consulta, edición y validación de horarios.

Endpoints (PLAN §7):
  · POST  /horarios/generar      (T-021) ejecuta el motor CSP y persiste.
  · POST  /horarios/vacio         crea un horario en blanco (estado borrador).
  · GET   /horarios              (T-024) lista horarios guardados.
  · GET   /horarios/{id}         (T-024) devuelve horario + sus celdas.
  · POST  /horarios/{id}/editar  (T-023) mueve/agrega una celda validando en vivo.
  · DELETE /horarios/{id}/celdas/{celda_id}  elimina una celda de un horario.
  · POST  /horarios/validar      (T-022) verifica restricciones de un horario.
"""

from __future__ import annotations

from datetime import time

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.auth import get_current_user
from app.db import get_db
from app.models.celdas import CeldaOut
from app.models.horarios import HorarioOut
from app.scheduler import load_problem, solve, validate_cell_move, validate_schedule

router = APIRouter(
    prefix="/horarios",
    tags=["Horarios"],
    dependencies=[Depends(get_current_user)],
)


# ---------------------------------------------------------------------------
# Persistencia (transacción única por operación)
# ---------------------------------------------------------------------------


def _insert_horario(
    conn: psycopg.Connection,
    configuracion_id: int,
    nombre: str,
    estado: str,
    usuario_id: str,
) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO horarios (configuracion_id, nombre, estado, usuario_id)
            VALUES (%s, %s, %s, %s)
            RETURNING *
            """,
            (configuracion_id, nombre, estado, usuario_id),
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


def _load_horario(conn: psycopg.Connection, horario_id: int, usuario_id: str) -> dict:
    """Devuelve un horario solo si pertenece al usuario (404 en caso contrario)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM horarios WHERE id = %s AND usuario_id = %s",
            (horario_id, usuario_id),
        )
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


def _parse_hora(valor: time | str | None) -> time | None:
    """Normaliza "HH:MM:SS" del payload a `datetime.time` (como devuelve
    psycopg y como produce el solver); si ya es `time` lo deja igual."""
    if isinstance(valor, str):
        partes = valor.split(":")
        h = int(partes[0])
        m = int(partes[1]) if len(partes) > 1 else 0
        s = int(partes[2]) if len(partes) > 2 else 0
        return time(h, m, s)
    return valor


def _recalcular_estado(conn: psycopg.Connection, horario_id: int) -> str:
    """Recalcula y persiste el estado del horario según sus celdas actuales.

    Reglas (espejo de la semántica del solver):
      · Sin celdas                             → `borrador`.
      · Con celdas y 0 violaciones             → `completo`.
      · Con celdas y alguna violación          → `parcial`.

    Corre `load_problem` + `validate_schedule` como `validar_horario`. Si no
    hubiera configuración activa no se puede validar, así que se conserva un
    estado prudente por conteo (`borrador` sin celdas, `parcial` con celdas)
    en lugar de fallar la operación de edición que la invocó.
    """
    celdas = _load_celdas_de(conn, horario_id)
    if not celdas:
        estado = "borrador"
    else:
        problem, error = load_problem(conn, horario_id)
        if error:
            estado = "parcial"
        else:
            violaciones = validate_schedule(problem, celdas)
            estado = "completo" if not violaciones else "parcial"

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE horarios SET estado = %s WHERE id = %s",
            (estado, horario_id),
        )
    return estado


# ---------------------------------------------------------------------------
# T-021 · Generar horario con el motor CSP
# ---------------------------------------------------------------------------


@router.post("/generar", status_code=status.HTTP_201_CREATED)
def generar(
    payload: dict,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Ejecuta el motor CSP y persiste horario + celdas en una transacción.

    Body opcional:
      · `nombre` → etiqueta del horario (por defecto "Horario").
      · `horario_id` → si se pasa, regenera SOBRE un horario existente
        conservando sus celdas `bloqueada = true` (inmutables) y respetando su
        configuración; en caso contrario usa la configuración activa.
    """
    usuario_id = usuario["sub"]
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
                # Regeneración: conservamos el id, limpiamos celdas y volvemos
                # a estado "borrador" (el trigger de completitud se dispara al
                # transitar a "completo", DESPUÉS de reinsertar las celdas).
                _load_horario(conn, horario_id, usuario_id)
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM celdas WHERE horario_id = %s",
                        (horario_id,),
                    )
                    cur.execute(
                        "UPDATE horarios SET nombre = %s, estado = 'borrador' WHERE id = %s",
                        (nombre, horario_id),
                    )
            else:
                config_id = problem.jornada.config_id
                horario = _insert_horario(conn, config_id, nombre, "borrador", usuario_id)
                horario_id = horario["id"]

            # Primero las celdas, luego el estado: el trigger sch_horario_validar
            # valida completitud/intensidad/carga con las celdas ya presentes.
            celdas = _insert_celdas(conn, horario_id, resultado.celdas) if resultado.celdas else []

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE horarios SET estado = %s WHERE id = %s",
                    (resultado.estado, horario_id),
                )
            horario = _load_horario(conn, horario_id, usuario_id)
            horario["estado"] = resultado.estado
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
# Horario en blanco (inicio de la edición manual 100 % a mano)
# ---------------------------------------------------------------------------


@router.post("/vacio", status_code=status.HTTP_201_CREATED)
def crear_vacio(
    payload: dict,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Crea un horario vacío (`estado='borrador'`, 0 celdas).

    Body opcional: `{"nombre": ...}` (por defecto "Horario en blanco").
    Requiere una configuración de jornada activa (409 si no la hay, igual que
    `generar`). Devuelve la misma forma que `generar` con celdas vacías.
    """
    usuario_id = usuario["sub"]
    nombre = str(payload.get("nombre", "Horario en blanco"))

    problem, error = load_problem(conn, None)
    if error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error["detail"])

    horario = _insert_horario(conn, problem.jornada.config_id, nombre, "borrador", usuario_id)

    return {
        "horario": horario,
        "estado": "borrador",
        "completo": False,
        "celdas": [],
        "conflictos": [],
        "avisos": [],
        "statistics": {
            "variables": 0,
            "asignadas": 0,
            "fijas": 0,
            "nodos_explorados": 0,
            "tiempo_seg": 0.0,
        },
    }


# ---------------------------------------------------------------------------
# T-024 · Consulta de horarios
# ---------------------------------------------------------------------------


@router.get("", response_model=list[HorarioOut])
def list_horarios(
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> list[dict]:
    """Lista los horarios del usuario actual (más recientes primero)."""
    usuario_id = usuario["sub"]
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM horarios WHERE usuario_id = %s ORDER BY id DESC",
            (usuario_id,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.get("/{horario_id}")
def get_horario(
    horario_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Devuelve un horario con todas sus celdas (solo si es del usuario)."""
    usuario_id = usuario["sub"]
    horario = _load_horario(conn, horario_id, usuario_id)
    celdas = _load_celdas_de(conn, horario_id)
    return {"horario": horario, "celdas": celdas}


# ---------------------------------------------------------------------------
# T-022 · Validación de restricciones de un horario guardado
# ---------------------------------------------------------------------------


@router.post("/validar")
def validar_horario(
    payload: dict,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Verifica todas las restricciones de un horario y las reporta.

    Body: `{"horario_id": <id>}`. Devuelve `violaciones` (cada una con tipo y
    mensaje). Si la lista está vacía → horario válido.
    """
    usuario_id = usuario["sub"]
    horario_id = payload.get("horario_id")
    _load_horario(conn, horario_id, usuario_id)
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
    "bloqueada",
)


@router.post("/{horario_id}/editar")
def editar_celda(
    horario_id: int,
    payload: dict,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Agrega o mueve una celda validando en tiempo real.

    Body:
      · `celda_id` (opcional) → si se pasa, es un MOVIMIENTO de esa celda
        (los campos no enviados conservan su valor actual).
      · Ningún `celda_id` → se crea una celda nueva con los campos dados.
      · `curso_id` es obligatorio y no cambia en un movimiento.
      · `bloqueada` (opcional) → en un movimiento, fija (`true`) o suelta
        (`false`) la celda sin cambiar su ubicación ni asignación.

    La validación simula la celda final contra el resto; si hay violaciones de
    choque/disponibilidad/salón/jornada se responde 409 sin guardar nada.
    """
    usuario_id = usuario["sub"]
    # Verificar ownership del horario antes de cualquier operación.
    _load_horario(conn, horario_id, usuario_id)

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

    # El payload trae horas como "HH:MM:SS"; la validación y el INSERT usan
    # objetos `time` (los mismos que psycopg devuelve y que produce el solver).
    for k in ("hora_inicio", "hora_fin"):
        propuesta[k] = _parse_hora(propuesta.get(k))

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
    # 3) Estado del horario tras la mutación (se persiste en la BD).
    estado = _recalcular_estado(conn, horario_id)
    return {
        "valido": True,
        "celda": dict(fila),
        "advertencias": advertencias,
        "estado": estado,
    }


# ---------------------------------------------------------------------------
# Borrar una celda del horario (edición manual)
# ---------------------------------------------------------------------------


@router.delete("/{horario_id}/cursos/{curso_id}/celdas")
def vaciar_curso(
    horario_id: int,
    curso_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Elimina únicamente las celdas de un curso dentro del horario."""
    usuario_id = usuario["sub"]
    _load_horario(conn, horario_id, usuario_id)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM celdas WHERE horario_id = %s AND curso_id = %s RETURNING id",
                (horario_id, curso_id),
            )
            eliminadas = len(cur.fetchall())
        estado = _recalcular_estado(conn, horario_id)

    return {
        "eliminadas": eliminadas,
        "horario_id": horario_id,
        "curso_id": curso_id,
        "estado": estado,
    }


@router.delete("/{horario_id}/celdas/{celda_id}")
def borrar_celda(
    horario_id: int,
    celda_id: int,
    conn: psycopg.Connection = Depends(get_db),
    usuario: dict = Depends(get_current_user),
) -> dict:
    """Elimina una celda del horario (solo si le pertenece).

    404 si la celda no existe o no pertenece al horario. Tras borrar, recalcula
    y persiste el estado del horario (`_recalcular_estado`) y lo devuelve.
    """
    usuario_id = usuario["sub"]
    _load_horario(conn, horario_id, usuario_id)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "DELETE FROM celdas WHERE id = %s AND horario_id = %s RETURNING *",
            (celda_id, horario_id),
        )
        fila = cur.fetchone()
    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Celda {celda_id} no encontrada en el horario {horario_id}.",
        )

    estado = _recalcular_estado(conn, horario_id)
    return {
        "eliminada": True,
        "celda_id": celda_id,
        "horario_id": horario_id,
        "estado": estado,
    }
