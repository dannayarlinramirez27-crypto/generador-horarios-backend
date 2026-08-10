"""T-022/T-023 · Validación de restricciones de un horario.

Reutilizado por:
  · `POST /api/v1/horarios/validar`  → chequea todo un horario guardado.
  · `POST /api/v1/horarios/{id}/editar` → valida un movimiento de celda en
    tiempo real contra el resto de las celdas (simula la celda nueva).

Reglas implementadas (espejo del trigger `sch_celda_validar` del esquema SQL):
  choques de curso/docente/salón en (día,bloque), disponibilidad del docente,
  asignación docente↔materia y docente↔curso, tipo de salón acorde a la materia,
  política "no última hora", jornada/días laborables y carga académica.
"""

from __future__ import annotations

from datetime import time

from app.scheduler.models import Problem
from app.scheduler.models import diff_min


def _blocks_de_celda(celda: dict, mb: int) -> int:
    """Bloques que ocupa una celda (redondea al bloque entero más cercano)."""
    minutos = diff_min(celda["hora_inicio"], celda["hora_fin"])
    return max(1, round(minutos / mb))


def _report(tipo: str, mensaje: str, celda_id: int | None = None, **extra) -> dict:
    return {"tipo": tipo, "mensaje": mensaje, "celda_id": celda_id, **extra}


def validate_schedule(problem: Problem, celdas: list[dict]) -> list[dict]:
    """Valida todas las celdas de un horario. Devuelve lista de violaciones."""
    errores: list[dict] = []
    mb = problem.minutos_bloque
    jornada = problem.jornada
    dias_laborables = set(jornada.dias)
    materias = problem.materias
    salones = {s.id: s for s in problem.salones}
    docentes = {d.id: d for d in problem.docentes}

    # --- Choques por recurso en (dia, bloque) ---
    por_curso: dict = {}
    por_docente: dict = {}
    por_salon: dict = {}
    carga_docente: dict[int, int] = {}
    horas_curso: dict[int, int] = {}

    for celda in celdas:
        cid = celda.get("id")
        dia, bloque = celda["dia"], celda["bloque"]
        clave = (dia, bloque)

        # 1) Choque de curso
        prev = por_curso.get((celda["curso_id"],) + clave)
        if prev is not None:
            errores.append(_report("choque_curso",
                f"El curso ya tiene clase en (día {dia}, bloque {bloque}).", cid))
        else:
            por_curso[(celda["curso_id"],) + clave] = cid

        # 2) Choque de docente
        prev = por_docente.get((celda["docente_id"],) + clave)
        if prev is not None:
            errores.append(_report("choque_docente",
                f"El docente tiene dos clases en (día {dia}, bloque {bloque}).", cid))
        else:
            por_docente[(celda["docente_id"],) + clave] = cid

        # 3) Choque de salón
        prev = por_salon.get((celda["salon_id"],) + clave)
        if prev is not None:
            errores.append(_report("choque_salon",
                f"El salón está ocupado dos veces en (día {dia}, bloque {bloque}).", cid))
        else:
            por_salon[(celda["salon_id"],) + clave] = cid

        # 4) Día laborable
        if dia not in dias_laborables:
            errores.append(_report("dia_no_laborable",
                f"El día {dia} no es laborable según la jornada.", cid))

        # 5) Dentro de la jornada
        if celda["hora_inicio"] < jornada.hora_inicio or celda["hora_fin"] > jornada.hora_fin:
            errores.append(_report("fuera_jornada",
                f"La clase {celda['hora_inicio']}-{celda['hora_fin']} excede la jornada.", cid))

        # 6) Docente asignado a la materia y al curso
        doc = docentes.get(celda["docente_id"])
        if doc is not None:
            if celda["materia_id"] not in doc.materias:
                errores.append(_report("docente_sin_materia",
                    "El docente no está designado para dictar esa materia.", cid))
            if celda["curso_id"] not in doc.cursos:
                errores.append(_report("docente_sin_curso",
                    "El docente no está asignado a ese curso.", cid))

        # 7) Disponibilidad del docente
        if doc is not None and not _en_ventana(
            doc.ventanas, dia, celda["hora_inicio"], celda["hora_fin"]
        ):
            errores.append(_report("sin_disponibilidad",
                "El docente no tiene disponibilidad en ese día y hora.", cid))

        # 8) Tipo de salón acorde a la materia
        mat = materias.get(celda["materia_id"])
        salon = salones.get(celda["salon_id"])
        if mat is not None and salon is not None:
            if mat.requiere_salon:
                if salon.tipo != mat.tipo_salon_requerido:
                    errores.append(_report("salon_incorrecto",
                        f"La materia requiere un espacio {mat.tipo_salon_requerido}; "
                        f"se asignó uno de tipo {salon.tipo}.", cid))
            elif salon.tipo != "aula":
                errores.append(_report("salon_no_aula",
                    "La materia no requiere laboratorio/sala; solo puede usar aulas.", cid))

        # 9) Política "no última hora"
        if mat is not None and mat.no_ultima_hora:
            slot = jornada.slot(dia, bloque)
            if slot is not None and slot.ultimo:
                errores.append(_report("ultima_hora",
                    "La materia no puede programarse en la última hora de la jornada.", cid))

        # 10) Carga académica del docente (en bloques)
        carga_docente[celda["docente_id"]] = (
            carga_docente.get(celda["docente_id"], 0)
            + _blocks_de_celda(celda, mb)
        )

        # 11) Horas semanales acumuladas por curso (para completitud)
        horas_curso[celda["curso_id"]] = (
            horas_curso.get(celda["curso_id"], 0)
            + _blocks_de_celda(celda, mb)
        )

    # 12) Carga académica por docente
    for d in problem.docentes:
        usados = carga_docente.get(d.id, 0)
        cap = d.carga_horaria * 60 // mb
        if usados > cap:
            errores.append(_report("carga_docente_excedida",
                f"El docente {d.nombre} {d.apellido} ocupa {usados} bloques; "
                f"su contrato permite {cap}.", doc_id=d.id))

    # 13) Completitud por curso (aviso: no bloquea la edición manual)
    avisos = []
    for curso in problem.cursos:
        puestos = horas_curso.get(curso.id, 0)
        meta = curso.horas_semanales * 60 // mb
        if puestos != meta:
            avisos.append(_report("carga_curso_incompleta",
                f"El curso {curso.nombre} lleva {puestos} bloques; se esperan {meta}.",
                curso_id=curso.id))

    return errores + avisos


def validate_cell_move(
    problem: Problem,
    otras_celdas: list[dict],
    nueva: dict,
) -> list[dict]:
    """Valida en tiempo real un movimiento de celda contra el resto.

    `otras_celdas` = celdas del horario EXCEPTO la que se mueve (o todas si es
    una celda nueva). Devuelve solo violaciones atribuibles al `nueva`.
    """
    # Reutilizamos el chequeo masivo montando el conjunto completo.
    simuladas = list(otras_celdas) + [nueva]
    todas = validate_schedule(problem, simuladas)
    # Nos quedamos con las violaciones de choque/disponibilidad/etc. que
    # involucran a la nueva celda; las de "carga_curso_incompleta" se omiten
    # porque son globales y no impiden un movimiento individual.
    relevantes = [
        v for v in todas if v.get("celda_id") is None or v["celda_id"] == nueva.get("id")
    ]
    return [v for v in relevantes if v["tipo"] != "carga_curso_incompleta"]


def _en_ventana(
    ventanas: list[tuple[int, time, time]], dia: int, h_ini: time, h_fin: time
) -> bool:
    for d, ws, we in ventanas:
        if (
            d == dia
            and ws <= h_ini
            and we >= h_fin
        ):
            return True
    return False