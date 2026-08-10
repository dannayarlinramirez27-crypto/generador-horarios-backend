"""T-016 · Asignación de intensidad horaria semanal por materia.

Antes de buscar la grilla, cada curso necesita saber CUÁNTOS bloques se dan de
cada una de sus materias. Este módulo resuelve ese subproblema combinatorio:

    elegir `bloques_i ∈ [bloque_min_i, bloque_max_i]` por materia
    tal que   Σ bloques_i == bloques_totales_del_curso

Los rangos `[min_horas, max_horas]` (de la tabla `materias`) se convierten a
bloques usando `minutos_bloque` de la jornada. El total por curso deriva de
`horas_semanales` (30 h grados 6-9, 37 h media técnica), redondeado a bloques.

Se resuelve con un DP sobre sumas alcanzables (∃ exacto), y si no existe
combinación exacta se reporta qué curso/materia lo impide (el solver quedará
en estado `parcial`).
"""

from __future__ import annotations

import math
from collections import defaultdict

from app.scheduler.models import Curso, Jornada, Materia, Problem


def _bloque_min_max(materia: Materia, minutos_bloque: int) -> tuple[int, int]:
    """Convierte [min_horas, max_horas] a rango de bloques enteros."""
    lo = math.ceil(materia.min_horas * 60 / minutos_bloque)
    hi = math.floor(materia.max_horas * 60 / minutos_bloque)
    return max(1, lo), max(1, hi)


def _total_bloques(curso: Curso, minutos_bloque: int) -> int:
    """Bloques semanales totales del curso (floordiv: sin superar horas)."""
    return curso.horas_semanales * 60 // minutos_bloque


def _materias_del_curso(problem: Problem, curso_id: int) -> set[int]:
    """Materias de un curso = unión de las materias de sus docentes.

    El modelo relacional no liga curso→materia directamente; un curso recibe
    las materias que dictan los docentes que le fueron asignados
    (`docente_curso` ∩ `docente_materia`).
    """
    materias: set[int] = set()
    for d in problem.docentes:
        if curso_id in d.cursos:
            materias |= d.materias
    return materias


def _dp_exacto(
    items: list[tuple[int, Materia, int, int]], total: int, minutos_bloque: int
) -> dict[int, int] | None:
    """Mesh exacta: devuelve {materia_id: bloques} o None si es imposible.

    `items` = [(curso_materia_identificador, materia, lo, hi)].
    DP de mochila acotada: dp[s] = alcanzable, con reconstrucción de camino.
    """
    dp: dict[int, tuple[int, int, int] | None] = {0: None}
    for i, (_cid, materia, lo, hi) in enumerate(items):
        ndp = dict(dp)
        for s, _ptr in list(dp.items()):
            for c in range(lo, hi + 1):
                ns = s + c
                if ns <= total and ns not in ndp:
                    ndp[ns] = (i, c, s)
        dp = ndp
        if total in dp:
            break

    if total not in dp:
        return None

    result: dict[int, int] = defaultdict(int)
    s = total
    ptr = dp[s]
    while ptr is not None:
        i, c, prev = ptr
        _cid, materia, _lo, _hi = items[i]
        result[materia.id] += c
        s = prev
        ptr = dp[s]
    return dict(result)


def allocate_intensities(problem: Problem) -> tuple[dict[int, dict[int, int]], list[dict]]:
    """Asigna `{curso_id: {materia_id: bloques}}`.

    Devuelve además una lista de avisos descriptivos con los cursos cuyos
    rangos impiden cuadrar el total exacto (dejarlos con `bloqueada` sin
    cambios implica estado `parcial` en el solver).
    """
    mb = problem.minutos_bloque
    plan: dict[int, dict[int, int]] = {}
    avisos: list[dict] = []

    for curso in problem.cursos:
        materia_ids = _materias_del_curso(problem, curso.id)
        if not materia_ids:
            avisos.append(
                {
                    "tipo": "curso_sin_materias",
                    "curso_id": curso.id,
                    "mensaje": (
                        f"El curso {curso.nombre} no tiene materias asignadas "
                        "(ningún docente le dicta materias)."
                    ),
                }
            )
            continue

        total = _total_bloques(curso, mb)
        items: list[tuple[int, Materia, int, int]] = []
        for mid in sorted(materia_ids):
            materia = problem.materias.get(mid)
            if materia is None:
                continue
            lo, hi = _bloque_min_max(materia, mb)
            if hi < lo:
                hi = lo
            items.append((curso.id, materia, lo, hi))

        if not items:
            avisos.append(
                {
                    "tipo": "curso_sin_materias_validas",
                    "curso_id": curso.id,
                    "mensaje": f"El curso {curso.nombre} no tiene materias válidas.",
                }
            )
            continue

        asignada = _dp_exacto(items, total, mb)
        if asignada is None:
            sum_lo = sum(lo for _, _, lo, _ in items)
            sum_hi = sum(hi for _, _, _, hi in items)
            avisos.append(
                {
                    "tipo": "intensidad_imposible",
                    "curso_id": curso.id,
                    "mensaje": (
                        f"El curso {curso.nombre} requiere {total} bloques, pero "
                        f"el rango total de sus materias es [{sum_lo}, {sum_hi}]."
                    ),
                }
            )
            continue

        plan[curso.id] = asignada

    return plan, avisos