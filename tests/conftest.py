"""Fixtures sinteticas (en memoria) para los tests del motor CSP.

No se toca la base de datos: se construye un `Problem` (app.scheduler.models)
completo pero pequeno y resoluble, que comparten los tests de solver,
intensidad, validacion y del router de regeneracion.

Jornada: tipo "unica", dias [1..5], 07:00-13:00, bloques de 60 min
=> 6 bloques/dia => 30 slots semanales.
"""

from datetime import time

import pytest

from app.scheduler.intensity import allocate_intensities
from app.scheduler.models import Curso, Docente, Jornada, Materia, Problem, Salon

_TOTAL_HORAS = 30
# Nombre, (min_horas, max_horas) por materia. Rangos elegidos para que el total
# [suma_min, suma_max] = [24, 31] permita cuadrar exactamente 30 bloques
# (bloque de 60 min => las horas coinciden con los bloques).
_MATERIAS = (
    (1, "Matematicas", (5, 6)),
    (2, "Lengua", (4, 5)),
    (3, "Historia", (4, 5)),
    (4, "Ingles", (4, 5)),
    (5, "Ed. Fisica", (1, 2)),
    (6, "Ciencias Naturales", (3, 4)),
    (7, "Informatica", (3, 4)),
)
# Materias que exigen salon de laboratorio (ids 6 y 7).
_LABORATORIO = {6, 7}


def _construir_problem() -> Problem:
    """Problema pequeño y resoluble: 2 cursos x 30 bloques = 60 celdas."""
    jornada = Jornada(
        config_id=1,
        tipo="unica",
        dias=[1, 2, 3, 4, 5],
        hora_inicio=time(7, 0),
        hora_fin=time(13, 0),
        minutos_bloque=60,
    )
    jornada.build_slots()

    cursos = [
        Curso(id=1, nombre="Primero", nivel="1", horas_semanales=_TOTAL_HORAS),
        Curso(id=2, nombre="Segundo", nivel="2", horas_semanales=_TOTAL_HORAS),
    ]

    materias: dict[int, Materia] = {}
    for mid, nombre, (min_horas, max_horas) in _MATERIAS:
        requiere_lab = mid in _LABORATORIO
        materias[mid] = Materia(
            id=mid,
            nombre=nombre,
            categoria="general",
            min_horas=min_horas,
            max_horas=max_horas,
            requiere_salon=requiere_lab,
            tipo_salon_requerido="laboratorio" if requiere_lab else None,
            no_ultima_hora=False,
        )

    # 5 aulas (1-5), 2 laboratorios (6-7) y 1 sala (8).
    salones = [
        Salon(id=i, nombre=f"Salon {i}", tipo=tipo, capacidad=30)
        for i, tipo in zip(range(1, 9), ("aula", "aula", "aula", "aula", "aula", "laboratorio", "laboratorio", "sala"))
    ]

    # Cada docente dicta una sola materia a AMBOS cursos, con disponibilidad
    # completa de lunes a viernes (07:00-13:00) y carga para 30 bloques.
    ventanas = [(dia, time(7, 0), time(13, 0)) for dia in range(1, 6)]
    docentes = [
        Docente(
            id=mid,
            nombre="Docente",
            apellido=str(mid),
            carga_horaria=_TOTAL_HORAS,
            ventanas=list(ventanas),
            materias={mid},
            cursos={1, 2},
        )
        for mid, _nombre, _rango in _MATERIAS
    ]

    return Problem(
        jornada=jornada,
        cursos=cursos,
        materias=materias,
        salones=salones,
        docentes=docentes,
        celdas_fijas=[],
    )


@pytest.fixture
def problem_ok() -> Problem:
    """Instancia `Problem` sintetica, sin base de datos."""
    return _construir_problem()


@pytest.fixture
def plan_ok(problem_ok) -> dict[int, dict[int, int]]:
    """Plan de intensidad `{curso_id: {materia_id: bloques}}` del `problem_ok`."""
    plan, _avisos = allocate_intensities(problem_ok)
    return plan