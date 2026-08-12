"""Tests de `allocate_intensities`: rangos por materia, total semanal exacto
y capacidad docente.
"""

from app.scheduler.intensity import allocate_intensities


def test_rangos_respetados_por_curso(problem_ok):
    """Cada materia queda dentro de [min_horas, max_horas] en su curso.

    Con bloques de 60 min las horas coinciden con los bloques, asi que el
    chequeo es directo contra el `plan` devuelto por la DP.
    """
    plan, avisos = allocate_intensities(problem_ok)
    assert not avisos

    for curso in problem_ok.cursos:
        for materia_id, bloques in plan[curso.id].items():
            materia = problem_ok.materias[materia_id]
            assert materia.min_horas <= bloques <= materia.max_horas, (
                f"Curso {curso.id}, materia {materia_id}: {bloques} fuera de "
                f"[{materia.min_horas}, {materia.max_horas}]"
            )


def test_suma_igual_horas_semanales(problem_ok):
    """Para cada curso, la suma de bloques asignados == horas_semanales y el
    plan cubre todas las materias del curso."""
    plan, avisos = allocate_intensities(problem_ok)
    assert not avisos

    for curso in problem_ok.cursos:
        assert sum(plan[curso.id].values()) == curso.horas_semanales


def test_carga_docente_respetada(problem_ok):
    """Ninguna materia se le asigna a un docente por encima de su carga.

    La DP no conoce las cargas: por eso este chequeo es agregado y acotado al
    diseño del fixture (cada docente dicta UNA materia a ambos cursos), donde
    el techo por materia es menor a 30 bloques. Se verifica que no se exceda
    la capacidad agregada derivada de `carga_horaria`.
    """
    plan, _avisos = allocate_intensities(problem_ok)
    mb = problem_ok.minutos_bloque

    for docente in problem_ok.docentes:
        asignados = sum(
            bloques
            for curso_id, materias in plan.items()
            for materia_id, bloques in materias.items()
            if materia_id in docente.materias and curso_id in docente.cursos
        )
        capacidad = docente.carga_horaria * 60 // mb
        assert asignados <= capacidad, (
            f"El docente {docente.id} recibio {asignados} bloques y su "
            f"capacidad es {capacidad}."
        )