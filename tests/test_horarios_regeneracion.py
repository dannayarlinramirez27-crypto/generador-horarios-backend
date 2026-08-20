"""REGRESION del fix en `POST /horarios/generar`: en la regeneracion con
`horario_id`, el estado debe transitar a "completo" SOLO DESPUES de insertar
las celdas (el trigger de BD `sch_horario_validar` valida con las celdas ya
presentes; si el UPDATE del estado corre antes, ve 0 celdas y rechaza).

La base de datos se simula con un fake que registra el ORDEN de las
operaciones SQL; `load_problem` y `solve` se sustituyen por stubs, de modo
que este test no toca Postgres ni red.
"""

from contextlib import nullcontext
from datetime import time

import app.routers.horarios as horarios_router
from app.scheduler.models import ScheduleResult

_HORARIO_ID = 17
_NOMBRE = "prueba"


class _CursorFake:
    """Cursor psycopg falso: registra cada SQL ejecutado en la conexion fake."""

    def __init__(self, conn: "_ConnFake") -> None:
        self._conn = conn

    def execute(self, sql: str, params=None) -> None:
        self._conn.sqls.append(sql)
        self._conn.params.append(params)

    def fetchone(self) -> dict:
        return self._conn.fila

    def fetchall(self) -> list[dict]:
        return self._conn.filas

    def __enter__(self) -> "_CursorFake":
        return self

    def __exit__(self, *_exc) -> bool:
        return False


class _ConnFake:
    """Conexion psycopg falsa: registra el orden de las operaciones SQL sin
    abrir ninguna conexion real."""

    def __init__(self) -> None:
        self.sqls: list[str] = []
        self.params: list = []
        self.fila: dict = {
            "id": _HORARIO_ID,
            "nombre": _NOMBRE,
            "configuracion_id": 1,
            "estado": "borrador",
            "usuario_id": "test-user-uuid",
        }
        self.filas: list[dict] = [self.fila]

    def cursor(self, row_factory=None) -> _CursorFake:
        return _CursorFake(self)

    def transaction(self):
        return nullcontext()


def _resultado_completo() -> ScheduleResult:
    """Resultado cook suficientemente real para el guardado: estado completo
    y dos celdas minimas (el solver real se sustituye en el test)."""
    return ScheduleResult(
        estado="completo",
        completo=True,
        celdas=[
            {
                "curso_id": 1,
                "materia_id": 1,
                "docente_id": 1,
                "salon_id": 1,
                "dia": 1,
                "bloque": 1,
                "hora_inicio": time(7, 0),
                "hora_fin": time(8, 0),
                "bloqueada": False,
            },
            {
                "curso_id": 2,
                "materia_id": 2,
                "docente_id": 2,
                "salon_id": 2,
                "dia": 1,
                "bloque": 1,
                "hora_inicio": time(7, 0),
                "hora_fin": time(8, 0),
                "bloqueada": False,
            },
        ],
        conflictos=[],
        avisos=[],
        statistics={},
    )


def test_generar_regeneracion_inserta_celdas_antes_del_estado_completo(
    monkeypatch, problem_ok
):
    """Al regenerar con `horario_id`, el orden registrado debe ser
    DELETE celdas -> INSERT celdas -> UPDATE horarios SET estado = 'completo'.

    Cubre exactamente el fix: el UPDATE que transita a "completo" debe correr
    DESPUES del primer INSERT INTO celdas (y de los DELETEs), nunca antes.
    """
    conn = _ConnFake()
    monkeypatch.setattr(
        horarios_router, "load_problem", lambda _conn, _hid: (problem_ok, None)
    )
    monkeypatch.setattr(horarios_router, "solve", lambda _problem: _resultado_completo())

    respuesta = horarios_router.generar(
        {"nombre": _NOMBRE, "horario_id": _HORARIO_ID},
        conn,
        {"sub": "test-user-uuid"},
    )

    operaciones = list(zip(conn.sqls, conn.params))

    idx_delete = next(
        i for i, (sql, _p) in enumerate(operaciones) if "DELETE FROM celdas" in sql
    )
    idx_insert = next(
        i for i, (sql, _p) in enumerate(operaciones) if "INSERT INTO celdas" in sql
    )
    idx_estado_completo = next(
        i
        for i, (sql, params) in enumerate(operaciones)
        if "UPDATE horarios" in sql
        and "SET estado" in sql
        and params
        and "completo" in params
    )

    # El estado solo puede pasar a "completo" despues de insertar las celdas.
    assert idx_delete < idx_insert < idx_estado_completo
    assert respuesta["estado"] == "completo"
    assert respuesta["horario"]["estado"] == "completo"