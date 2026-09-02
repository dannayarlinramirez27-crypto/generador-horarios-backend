"""Router para carga de datos de prueba (seed)."""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.db import get_db

router = APIRouter(
    prefix="/seed",
    tags=["Seed"],
)


# ---------------------------------------------------------------------------
# Datos de prueba
# ---------------------------------------------------------------------------

JORNADA_PRUEBA = {
    "nombre": "Configuración general",
    "tipo_jornada": "unica",
    "dias_laborables": [1, 2, 3, 4, 5],
    "hora_inicio": "07:00:00",
    "hora_fin": "13:00:00",
    "minutos_bloque": 60,
    "activa": True,
}

DOCENTES_PRUEBA = [
    {"nombre": "Ana García", "max_horas_semanales": 30},
    {"nombre": "Carlos López", "max_horas_semanales": 30},
    {"nombre": "María Rodríguez", "max_horas_semanales": 30},
]

MATERIAS_PRUEBA = [
    {"nombre": "Matemáticas", "horas_semanales": 4},
    {"nombre": "Español", "horas_semanales": 4},
    {"nombre": "Ciencias", "horas_semanales": 4},
]

CURSOS_PRUEBA = [
    {"nombre": "6A", "nivel": 6, "orden": 1},
    {"nombre": "6B", "nivel": 6, "orden": 2},
]


@router.post("", status_code=status.HTTP_201_CREATED)
def seed_data(
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Limpia e inserta datos de prueba mínimos para probar la generación de horarios."""
    resultados: dict = {}

    try:
        with conn.transaction():
            # 1. Limpiar tablas hijas primero (FK constraints)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM docente_materia")
                cur.execute("DELETE FROM docente_curso")
                cur.execute("DELETE FROM horarios_celdas")
                cur.execute("DELETE FROM horarios")
                cur.execute("DELETE FROM salones")
                cur.execute("DELETE FROM docentes")
                cur.execute("DELETE FROM materias")
                cur.execute("DELETE FROM cursos")
                cur.execute("DELETE FROM configs")
            resultados["limpieza"] = "ok"

            # 2. Jornada
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO configs (nombre, tipo_jornada, dias_laborables, hora_inicio, hora_fin, minutos_bloque, activa)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        JORNADA_PRUEBA["nombre"],
                        JORNADA_PRUEBA["tipo_jornada"],
                        JORNADA_PRUEBA["dias_laborables"],
                        JORNADA_PRUEBA["hora_inicio"],
                        JORNADA_PRUEBA["hora_fin"],
                        JORNADA_PRUEBA["minutos_bloque"],
                        JORNADA_PRUEBA["activa"],
                    ),
                )
            resultados["jornada"] = "creada"

            # 3. Docentes
            docentes_ids: list[int] = []
            with conn.cursor(row_factory=dict_row) as cur:
                for d in DOCENTES_PRUEBA:
                    cur.execute(
                        """
                        INSERT INTO docentes (nombre, max_horas_semanales, activo)
                        VALUES (%s, %s, true)
                        RETURNING id
                        """,
                        (d["nombre"], d["max_horas_semanales"]),
                    )
                    row = cur.fetchone()
                    if row:
                        docentes_ids.append(row["id"])
            resultados["docentes"] = len(docentes_ids)

            # 4. Materias
            materias_ids: list[int] = []
            with conn.cursor(row_factory=dict_row) as cur:
                for m in MATERIAS_PRUEBA:
                    cur.execute(
                        """
                        INSERT INTO materias (nombre, horas_semanales, activa)
                        VALUES (%s, %s, true)
                        RETURNING id
                        """,
                        (m["nombre"], m["horas_semanales"]),
                    )
                    row = cur.fetchone()
                    if row:
                        materias_ids.append(row["id"])
            resultados["materias"] = len(materias_ids)

            # 5. Cursos
            cursos_ids: list[int] = []
            with conn.cursor(row_factory=dict_row) as cur:
                for c in CURSOS_PRUEBA:
                    cur.execute(
                        """
                        INSERT INTO cursos (nombre, nivel, orden)
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        (c["nombre"], c["nivel"], c["orden"]),
                    )
                    row = cur.fetchone()
                    if row:
                        cursos_ids.append(row["id"])
            resultados["cursos"] = len(cursos_ids)

            # 6. Asignaciones docente ↔ materia
            asign_mat = 0
            with conn.cursor() as cur:
                for doc_id in docentes_ids:
                    for mat_id in materias_ids:
                        cur.execute(
                            """
                            INSERT INTO docente_materia (docente_id, materia_id)
                            VALUES (%s, %s)
                            """,
                            (doc_id, mat_id),
                        )
                        asign_mat += 1
            resultados["asignaciones_materias"] = asign_mat

            # 7. Asignaciones docente ↔ curso
            asign_cur = 0
            with conn.cursor() as cur:
                for doc_id in docentes_ids:
                    for cur_id in cursos_ids:
                        cur.execute(
                            """
                            INSERT INTO docente_curso (docente_id, curso_id)
                            VALUES (%s, %s)
                            """,
                            (doc_id, cur_id),
                        )
                        asign_cur += 1
            resultados["asignaciones_cursos"] = asign_cur

    except Exception as exc:
        print(f"[ERROR seed_data] {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al cargar datos de prueba: {exc}",
        ) from exc

    return {
        "ok": True,
        "mensaje": "Datos de prueba cargados correctamente",
        "detalle": resultados,
    }
