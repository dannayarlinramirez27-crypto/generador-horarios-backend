"""Tests de validacion de horarios (restricciones duras y movimientos).
"""

from app.scheduler.solver import solve
from app.scheduler.validation import validate_cell_move, validate_schedule


def test_horario_completo_sin_violaciones(problem_ok):
    """El resultado completo de `solve` no viola ninguna regla."""
    resultado = solve(problem_ok)
    assert resultado.estado == "completo"

    violaciones = validate_schedule(problem_ok, resultado.celdas)
    assert violaciones == []


def test_detecta_choque_docente(problem_ok):
    """Una celda artificial que repite (docente, dia, bloque) es reportada.

    Las celdas reciben un `id` (como en la BD): `validate_schedule` usa el id
    para recordar la celda previa en cada (dia, bloque); sin id, el choque no
    se distingue (el valor previo queda en `None`).
    """
    resultado = solve(problem_ok)
    assert resultado.estado == "completo"

    celdas = [dict(celda, id=i) for i, celda in enumerate(resultado.celdas)]
    duplicada = dict(celdas[0])  # mismo (docente, dia, bloque) que la original
    duplicada["id"] = 9999

    violaciones = validate_schedule(problem_ok, celdas + [duplicada])

    tipos = {v["tipo"] for v in violaciones}
    assert "choque_docente" in tipos


def test_validate_cell_move_rechaza_choque(problem_ok):
    """`validate_cell_move` rechaza una propuesta que choca contra las otras
    celdas (mismo salon/dia/bloque o docente); las violaciones son no vacias
    y no se omiten por ser de choque."""
    resultado = solve(problem_ok)
    assert resultado.estado == "completo"

    # Propuesta nueva que repite la celda 0: choca con el resto del horario.
    otras = [dict(celda, id=i) for i, celda in enumerate(resultado.celdas)]
    choque = dict(otras[0])
    choque["id"] = 9999

    violaciones = validate_cell_move(problem_ok, otras, choque)

    assert violaciones
    assert any(v["tipo"].startswith("choque") for v in violaciones)