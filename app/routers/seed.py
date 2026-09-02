"""Router para carga de datos de prueba (seed)."""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row

from app.auth import require_roles
from app.db import get_db

router = APIRouter(
    prefix="/seed",
    tags=["Seed"],
    dependencies=[Depends(require_roles(["admin"]))],
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
    {"nombre": "Ana", "apellido": "García", "documento": "12345678", "carga_horaria": 30, "activo": True},
    {"nombre": "Carlos", "apellido": "López", "documento": "23456789", "carga_horaria": 30, "activo": True},
    {"nombre": "María", "apellido": "Rodríguez", "documento": "34567890", "carga_horaria": 30, "activo": True},
    {"nombre": "Pedro", "apellido": "Martínez", "documento": "45678901", "carga_horaria": 30, "activo": True},
    {"nombre": "Laura", "apellido": "Sánchez", "documento": "56789012", "carga_horaria": 30, "activo": True},
]

MATERIAS_PRUEBA = [
    {"nombre": "Matemáticas", "categoria": "basica", "min_horas": 4, "max_horas": 5, "requiere_salon": False, "tipo_salon_requerido": None, "no_ultima_hora": False},
    {"nombre": "Español", "categoria": "basica", "min_horas": 4, "max_horas": 5, "requiere_salon": False, "tipo_salon_requerido": None, "no_ultima_hora": False},
    {"nombre": "Ciencias", "categoria": "basica", "min_horas": 3, "max_horas": 4, "requiere_salon": True, "tipo_salon_requerido": "laboratorio", "no_ultima_hora": False},
    {"nombre": "Inglés", "categoria": "basica", "min_horas": 3, "max_horas": 4, "requiere_salon": False, "tipo_salon_requerido": None, "no_ultima_hora": False},
    {"nombre": "Educación Física", "categoria": "otras", "min_horas": 2, "max_horas": 3, "requiere_salon": False, "tipo_salon_requerido": None, "no_ultima_hora": True},
]

CURSOS_PRUEBA = [
    {"nombre": "6A", "nivel": "6to", "horas_semanales": 30, "orden": 1},
    {"nombre": "6B", "nivel": "6to", "horas_semanales": 30, "orden": 2},
]

SALONES_PRUEBA = [
    {"nombre": "Aula 101", "tipo": "aula", "capacidad": 30, "activo": True},
    {"nombre": "Aula 102", "tipo": "aula", "capacidad": 30, "activo": True},
    {"nombre": "Laboratorio", "tipo": "laboratorio", "capacidad": 25, "activo": True},
]


@router.post("", status_code=status.HTTP_201_CREATED)
def seed_data(
    conn: psycopg.Connection = Depends(get_db),
) -> dict:
    """Inserta datos de prueba en la base de datos para probar la generación
    de horarios. Requiere rol admin. Es idempotente: no falla si los datos
    ya existen (ignora unique violations)."""
    resultados: dict = {}

    try:
        with conn.transaction():
            # 1. Jornada (desactiva la anterior si existe)
            with conn.cursor() as cur:
                cur.execute("UPDATE configs SET activa = false WHERE activa = true")
                cur.execute(
                    """
                    INSERT INTO configs (nombre, tipo_jornada, dias_laborables, hora_inicio, hora_fin, minutos_bloque, activa)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
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

            # 2. Docentes
            docentes_ids: list[int] = []
            with conn.cursor(row_factory=dict_row) as cur:
                for d in DOCENTES_PRUEBA:
                    cur.execute(
                        """
                        INSERT INTO docentes (nombre, apellido, documento, carga_horaria, activo)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (documento) DO UPDATE SET nombre=EXCLUDED.nombre, apellido=EXCLUDED.apellido
                        RETURNING id
                        """,
                        (d["nombre"], d["apellido"], d["documento"], d["carga_horaria"], d["activo"]),
                    )
                    row = cur.fetchone()
                    if row:
                        docentes_ids.append(row["id"])
            resultados["docentes"] = len(docentes_ids)

            # 3. Materias
            materias_ids: list[int] = []
            with conn.cursor(row_factory=dict_row) as cur:
                for m in MATERIAS_PRUEBA:
                    cur.execute(
                        """
                        INSERT INTO materias (nombre, categoria, min_horas, max_horas, requiere_salon, tipo_salon_requerido, no_ultima_hora)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (nombre) DO UPDATE SET categoria=EXCLUDED.categoria, min_horas=EXCLUDED.min_horas, max_horas=EXCLUDED.max_horas, requiere_salon=EXCLUDED.requiere_salon, tipo_salon_requerido=EXCLUDED.tipo_salon_requerido, no_ultima_hora=EXCLUDED.no_ultima_hora
                        RETURNING id
                        """,
                        (m["nombre"], m["categoria"], m["min_horas"], m["max_horas"], m["requiere_salon"], m["tipo_salon_requerido"], m["no_ultima_hora"]),
                    )
                    row = cur.fetchone()
                    if row:
                        materias_ids.append(row["id"])
            resultados["materias"] = len(materias_ids)

            # 4. Cursos
            cursos_ids: list[int] = []
            with conn.cursor(row_factory=dict_row) as cur:
                for c in CURSOS_PRUEBA:
                    cur.execute(
                        """
                        INSERT INTO cursos (nombre, nivel, horas_semanales, orden)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (nombre) DO UPDATE SET nivel=EXCLUDED.nivel, horas_semanales=EXCLUDED.horas_semanales, orden=EXCLUDED.orden
                        RETURNING id
                        """,
                        (c["nombre"], c["nivel"], c["horas_semanales"], c["orden"]),
                    )
                    row = cur.fetchone()
                    if row:
                        cursos_ids.append(row["id"])
            resultados["cursos"] = len(cursos_ids)

            # 5. Salones
            salones_ids: list[int] = []
            with conn.cursor(row_factory=dict_row) as cur:
                for s in SALONES_PRUEBA:
                    cur.execute(
                        """
                        INSERT INTO salones (nombre, tipo, capacidad, activo)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (nombre) DO UPDATE SET tipo=EXCLUDED.tipo, capacidad=EXCLUDED.capacidad, activo=EXCLUDED.activo
                        RETURNING id
                        """,
                        (s["nombre"], s["tipo"], s["capacidad"], s["activo"]),
                    )
                    row = cur.fetchone()
                    if row:
                        salones_ids.append(row["id"])
            resultados["salones"] = len(salones_ids)

            # 6. Asignaciones docente ↔ materia (todos los docentes a todas las materias)
            asign_mat = 0
            with conn.cursor() as cur:
                for doc_id in docentes_ids:
                    for mat_id in materias_ids:
                        cur.execute(
                            """
                            INSERT INTO docente_materia (docente_id, materia_id)
                            VALUES (%s, %s)
                            ON CONFLICT (docente_id, materia_id) DO NOTHING
                            """,
                            (doc_id, mat_id),
                        )
                        if cur.rowcount > 0:
                            asign_mat += 1
            resultados["asignaciones_materias"] = asign_mat

            # 7. Asignaciones docente ↔ curso (todos los docentes a todos los cursos)
            asign_cur = 0
            with conn.cursor() as cur:
                for doc_id in docentes_ids:
                    for cur_id in cursos_ids:
                        cur.execute(
                            """
                            INSERT INTO docente_curso (docente_id, curso_id)
                            VALUES (%s, %s)
                            ON CONFLICT (docente_id, curso_id) DO NOTHING
                            """,
                            (doc_id, cur_id),
                        )
                        if cur.rowcount > 0:
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
