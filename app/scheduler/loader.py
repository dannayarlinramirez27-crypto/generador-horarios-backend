"""T-015 · Carga de datos activos desde PostgreSQL/Supabase.

Lee la configuración activa, docentes activos (con su disponibilidad, materias
y cursos asignados), cursos, materias, salones activos y las celdas fijas
(`bloqueada = true`) de un horario, y los empaqueta en un `Problem` (CSP).

Todos los datos se cargan bajo demanda dentro del endpoint `generar`.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from app.scheduler.models import (
    CeldaFija,
    Curso,
    Docente,
    Jornada,
    Materia,
    Problem,
    Salon,
)


def _load_active_config(conn: psycopg.Connection) -> dict | None:
    """Devuelve la configuración de jornada activa (o la primera si hay varias)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM configs WHERE activa = true ORDER BY id LIMIT 1"
        )
        return cur.fetchone()


def _load_cursos(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM cursos ORDER BY nivel::int, orden, nombre")
        return cur.fetchall()


def _load_materias(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM materias ORDER BY id")
        return cur.fetchall()


def _load_salones(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM salones WHERE activo = true ORDER BY id")
        return cur.fetchall()


def _load_docentes(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM docentes WHERE activo = true ORDER BY id"
        )
        return cur.fetchall()


def _load_disponibilidades(
    conn: psycopg.Connection, docente_ids: list[int]
) -> dict[int, list[tuple[int, object, object]]]:
    """Ventanas horarias por docente: {docente_id: [(dia, hora_ini, hora_fin)]}."""
    result: dict[int, list[tuple[int, object, object]]] = {}
    if not docente_ids:
        return result
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT docente_id, dia, hora_inicio, hora_fin
            FROM disponibilidades
            WHERE docente_id = ANY(%s)
            ORDER BY docente_id, dia, hora_inicio
            """,
            (docente_ids,),
        )
        for docente_id, dia, h_ini, h_fin in cur.fetchall():
            result.setdefault(docente_id, []).append((dia, h_ini, h_fin))
    return result


def _load_asignaciones(conn: psycopg.Connection) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """Asignaciones docente→materia y docente→curso como sets por docente."""
    materias: dict[int, set[int]] = {}
    cursos: dict[int, set[int]] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT docente_id, materia_id FROM docente_materia")
        for docente_id, materia_id in cur.fetchall():
            materias.setdefault(docente_id, set()).add(materia_id)
        cur.execute("SELECT docente_id, curso_id FROM docente_curso")
        for docente_id, curso_id in cur.fetchall():
            cursos.setdefault(docente_id, set()).add(curso_id)
    return materias, cursos


def _load_celdas_fijas(
    conn: psycopg.Connection, horario_id: int | None
) -> list[dict]:
    """Celdas con `bloqueada = true` del horario a regenerar (inmutables)."""
    if horario_id is None:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT curso_id, materia_id, docente_id, salon_id, dia, bloque,
                   hora_inicio, hora_fin
            FROM celdas
            WHERE horario_id = %s AND bloqueada = true
            ORDER BY dia, bloque
            """,
            (horario_id,),
        )
        return cur.fetchall()


def load_problem(
    conn: psycopg.Connection, horario_id: int | None = None
) -> tuple[Problem, dict | None]:
    """Construye el `Problem` del CSP con los datos activos actuales.

    Devuelve `(problem, error)`: `error` es un dict con `detalle` si no hay
    configuración activa (no se puede generar un horario sin jornada).
    """
    config = _load_active_config(conn)
    if config is None:
        return Problem(jornada=Jornada(0, "unica", [], None, None, 0), cursos=[], materias={}, salones=[], docentes=[], celdas_fijas=[]), {
            "detail": "No hay una configuración de jornada activa. Crea una configuración y actívala."
        }

    jornada = Jornada(
        config_id=config["id"],
        tipo=config["tipo_jornada"],
        dias=list(config["dias_laborables"]),
        hora_inicio=config["hora_inicio"],
        hora_fin=config["hora_fin"],
        minutos_bloque=config["minutos_bloque"],
    )
    jornada.build_slots()

    cursos = [Curso(**{k: c[k] for k in ("id", "nombre", "nivel", "horas_semanales")}) for c in _load_cursos(conn)]

    materias_raw = _load_materias(conn)
    materias = {
        m["id"]: Materia(
            id=m["id"],
            nombre=m["nombre"],
            categoria=m["categoria"],
            min_horas=m["min_horas"],
            max_horas=m["max_horas"],
            requiere_salon=m["requiere_salon"],
            tipo_salon_requerido=m["tipo_salon_requerido"],
            no_ultima_hora=m["no_ultima_hora"],
        )
        for m in materias_raw
    }

    salones = [Salon(id=s["id"], nombre=s["nombre"], tipo=s["tipo"], capacidad=s["capacidad"]) for s in _load_salones(conn)]

    docentes_raw = _load_docentes(conn)
    docente_ids = [d["id"] for d in docentes_raw]
    ventanas = _load_disponibilidades(conn, docente_ids)
    asign_materias, asign_cursos = _load_asignaciones(conn)

    docentes: list[Docente] = []
    for d in docentes_raw:
        did = d["id"]
        docentes.append(
            Docente(
                id=did,
                nombre=d["nombre"],
                apellido=d["apellido"],
                carga_horaria=d["carga_horaria"],
                ventanas=ventanas.get(did, []),
                materias=asign_materias.get(did, set()),
                cursos=asign_cursos.get(did, set()),
            )
        )

    celdas_fijas = [
        CeldaFija(
            curso_id=c["curso_id"],
            materia_id=c["materia_id"],
            docente_id=c["docente_id"],
            salon_id=c["salon_id"],
            dia=c["dia"],
            bloque=c["bloque"],
            hora_inicio=c["hora_inicio"],
            hora_fin=c["hora_fin"],
        )
        for c in _load_celdas_fijas(conn, horario_id)
    ]

    problem = Problem(
        jornada=jornada,
        cursos=cursos,
        materias=materias,
        salones=salones,
        docentes=docentes,
        celdas_fijas=celdas_fijas,
    )
    return problem, None