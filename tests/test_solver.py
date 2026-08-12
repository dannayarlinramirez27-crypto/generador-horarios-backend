"""Tests del motor CSP (solver): grilla completa, ausencia de conflictos duros
y las regresiones del fix: el reinicio de `_deadline` antes del completado
greedy (T-029).
"""

import time

from app.scheduler.intensity import allocate_intensities
from app.scheduler.models import ScheduleResult
from app.scheduler.solver import TimeLimitReached, _Solver, solve


def _construir_solver(problem, plan: dict[int, dict[int, int]]) -> _Solver:
    """Crea un `_Solver` directo sobre el problema y su plan de intensidad."""
    cur_nombre = {c.id: c.nombre for c in problem.cursos}
    mat_nombre = {m.id: m.nombre for m in problem.materias.values()}
    return _Solver(problem, plan, cur_nombre, mat_nombre)


def test_solve_completa_toda_la_grilla(problem_ok):
    """El solver llena los 30 bloques de cada curso: 60 celdas en total,
    una por curso en cada uno de los 6 bloques de la jornada."""
    resultado = solve(problem_ok)

    assert resultado.estado == "completo"
    assert resultado.completo is True
    assert len(resultado.celdas) == 60
    assert resultado.conflictos == []

    por_curso: dict[int, int] = {}
    por_dia_bloque: dict[tuple[int, int], int] = {}
    por_bloque: dict[int, int] = {}
    for celda in resultado.celdas:
        por_curso[celda["curso_id"]] = por_curso.get(celda["curso_id"], 0) + 1
        clave = (celda["dia"], celda["bloque"])
        por_dia_bloque[clave] = por_dia_bloque.get(clave, 0) + 1
        por_bloque[celda["bloque"]] = por_bloque.get(celda["bloque"], 0) + 1

    # 30 celdas por curso y, en cada (dia, bloque), una por curso (2 en total;
    # ese (dia, bloque) se repite en 5 dias, por eso cada numero de bloque
    # suma 5 x 2 = 10 celdas).
    assert por_curso == {1: 30, 2: 30}
    assert por_dia_bloque == {
        (dia, bloque): 2 for dia in range(1, 6) for bloque in range(1, 7)
    }
    assert por_bloque == {b: 10 for b in range(1, 7)}


def test_sin_conflictos_duros(problem_ok):
    """No puede haber dos celdas que compartan (recurso, dia, bloque)."""
    resultado = solve(problem_ok)
    assert resultado.estado == "completo"

    def _sin_duplicados(campos: tuple[str, ...]) -> None:
        vistos: set[tuple] = set()
        for celda in resultado.celdas:
            clave = tuple(celda[campo] for campo in campos)
            assert clave not in vistos, f"Choque duro repetido: {campos} = {clave}"
            vistos.add(clave)

    _sin_duplicados(("docente_id", "dia", "bloque"))
    _sin_duplicados(("salon_id", "dia", "bloque"))
    _sin_duplicados(("curso_id", "dia", "bloque"))


def test_solve_reinicia_deadline_antes_del_greedy(monkeypatch, problem_ok):
    """REGRESION del fix de hoy: si el backtracking se trunca por tiempo, el
    completado greedy recibe una ventana propia y termina de llenar la grilla.

    Ajuste respecto del enunciado: sobre `problem_ok` el backtracking resuelve
    en ~60 nodos y nunca llega al chequeo de reloj (cada 256 nodos), asi que un
    `GREEDY_TRIGGER_SEG` minusculo por si solo no dispara la truncacion real.
    Ademas, `solve()` usa la MISMA constante para reiniciar la ventana del
    greedy; si fuera de 0.001s, el greedy tampoco alcanzaria a completar.
    Por eso se fuerza la truncacion de forma determinista: se sustituye
    `_backtrack` por un stub que simula una busqueda que consumio su ventana
    (deja `_deadline` vencido) y lanza `TimeLimitReached`, exactamente el
    punto donde la solucion real llega con el reloj caducado. Antes del fix,
    `_deadline` quedaba vencido, el greedy abandonaba en la primera iteracion
    y la grilla quedaba parcial; hoy la ventana se reinicia y se completa.
    """
    from app.scheduler import solver as solver_mod

    def _backtrack_truncado(self) -> None:
        # Simula el corte real: la busqueda agoto su ventana de tiempo.
        self._deadline = time.time() - 1
        raise TimeLimitReached()

    monkeypatch.setattr(solver_mod._Solver, "_backtrack", _backtrack_truncado)

    resultado = solve(problem_ok)

    # Se recorrio el camino truncado -> greedy (aviso del limite de tiempo).
    assert any(a["tipo"] == "limite_tiempo" for a in resultado.avisos)
    assert resultado.estado == "completo"
    assert resultado.completo is True
    assert len(resultado.celdas) == 60
    assert resultado.conflictos == []


def test_rellenar_greedy_con_deadline_vencido_no_rompe_a_medio_camino(
    problem_ok, plan_ok
):
    """REGRESION directa: `_rellenar_greedy` con `_deadline` vencido no debe
    lanzar ni dejar un estado inconsistente; simplemente abandona de inmediato
    la reasignacion (el reinicio del deadline ocurre dentro de `solve`)."""
    solver = _construir_solver(problem_ok, plan_ok)
    solver._deadline = time.time() - 1

    solver._rellenar_greedy()  # no debe levantar ninguna excepcion

    # El estado posterior sigue siendo consultable y serializable.
    resultado = solver.resultado(len(solver.vars))
    assert isinstance(resultado, ScheduleResult)


def test_allocate_intensities_consistente_con_el_solver(problem_ok):
    """La suma del plan usado por el solver coincide con la grilla generada."""
    plan, avisos = allocate_intensities(problem_ok)
    assert not avisos

    resultado = solve(problem_ok)
    por_curso: dict[int, int] = {}
    for celda in resultado.celdas:
        por_curso[celda["curso_id"]] = por_curso.get(celda["curso_id"], 0) + 1

    for curso_id, total_planificado in plan.items():
        assert por_curso[curso_id] == sum(total_planificado.values())