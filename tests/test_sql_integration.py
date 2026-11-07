"""T-037 — Suite de integracion SQL: triggers + RLS (regresion).

Verifica que los triggers de validacion (`sch_celda_validar`,
`sch_horario_validar`) y las politicas RLS siguen funcionando
correctamente tras los cambios de T-039 (aislamiento por usuario).

Conexion: usa `DATABASE_URL` del `.env` del backend.
Cada test abre una transaccion y hace ROLLBACK al terminar ->
no deja datos residuales en la base.

Ejecucion:
    pytest tests/test_sql_integration.py -v
"""

import json
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

# -- Helpers de conexion --


def _conninfo() -> str:
    """Lee DATABASE_URL del .env del backend (mismo patron que app/config.py)."""
    from app.config import get_settings

    return get_settings().database_url_value


@pytest.fixture
def db_conn():
    """Conexion transaccional: todo se revierte al final del test."""
    conn = psycopg.connect(_conninfo(), autocommit=False, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def seed(db_conn):
    """Crea datos de prueba minimos y devuelve los IDs.

    Estructura:
      - Config: jornada 07:00-13:00, L-V, bloques 60 min
      - Docente: carga 2h, disponible L-V 07:00-13:00
      - Materia: 'TestMat T037', min=1 max=2, aula
      - Salon: 'TestAula T037', aula
      - Curso: 'TestCurso T037', 2h semanales
      - docente_materia + docente_curso
      - Horario en borrador
    """
    cur = db_conn.cursor()
    _uid = uuid.uuid4().hex[:8]

    cur.execute(
        """INSERT INTO configs (nombre, tipo_jornada, dias_laborables,
               hora_inicio, hora_fin, minutos_bloque, activa)
           VALUES (%s, 'unica', '{1,2,3,4,5}',
                   '07:00:00', '13:00:00', 60, false)
           RETURNING id""",
        (f"TestCfg {_uid}",),
    )
    cfg_id = cur.fetchone()["id"]

    cur.execute(
        """INSERT INTO docentes (nombre, apellido, documento, carga_horaria, activo)
           VALUES ('Test', 'T037', %s, 2, true)
           RETURNING id""",
        (f"T037-{_uid}",),
    )
    doc_id = cur.fetchone()["id"]

    for dia in range(1, 6):
        cur.execute(
            """INSERT INTO disponibilidades (docente_id, dia, hora_inicio, hora_fin)
               VALUES (%s, %s, '07:00:00', '13:00:00')""",
            (doc_id, dia),
        )

    cur.execute(
        """INSERT INTO materias (nombre, categoria, min_horas, max_horas,
               requiere_salon, no_ultima_hora)
           VALUES (%s, 'basica', 1, 2, false, false)
           RETURNING id""",
        (f"TestMat {_uid}",),
    )
    mat_id = cur.fetchone()["id"]

    cur.execute(
        """INSERT INTO salones (nombre, tipo, capacidad, activo)
           VALUES (%s, 'aula', 30, true)
           RETURNING id""",
        (f"TestAula {_uid}",),
    )
    salon_id = cur.fetchone()["id"]

    cur.execute(
        """INSERT INTO cursos (nombre, nivel, horas_semanales)
           VALUES (%s, 'T', 2)
           RETURNING id""",
        (f"TestCurso {_uid}",),
    )
    cur_id = cur.fetchone()["id"]

    cur.execute(
        "INSERT INTO docente_materia (docente_id, materia_id) VALUES (%s, %s)",
        (doc_id, mat_id),
    )
    cur.execute(
        "INSERT INTO docente_curso (docente_id, curso_id) VALUES (%s, %s)",
        (doc_id, cur_id),
    )

    cur.execute(
        """INSERT INTO horarios (configuracion_id, nombre, estado)
           VALUES (%s, %s, 'borrador')
           RETURNING id""",
        (cfg_id, f"TestHor {_uid}"),
    )
    hor_id = cur.fetchone()["id"]

    # No commit — todo se revierte con rollback al final del test

    return {
        "cfg_id": cfg_id,
        "doc_id": doc_id,
        "mat_id": mat_id,
        "salon_id": salon_id,
        "cur_id": cur_id,
        "hor_id": hor_id,
    }


def _insert_celda(cur, hor_id, cur_id, mat_id, doc_id, salon_id,
                  dia, bloque, hi="07:00:00", hf="08:00:00", owner_id=None):
    """Helper: inserta una celda con los valores dados."""
    if owner_id is None:
        cur.execute(
            """INSERT INTO celdas (horario_id, curso_id, materia_id, docente_id,
                   salon_id, dia, bloque, hora_inicio, hora_fin, bloqueada)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false)""",
            (hor_id, cur_id, mat_id, doc_id, salon_id, dia, bloque, hi, hf),
        )
    else:
        cur.execute(
            """INSERT INTO celdas (horario_id, user_id, curso_id, materia_id, docente_id,
                   salon_id, dia, bloque, hora_inicio, hora_fin, bloqueada)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)""",
            (hor_id, owner_id, cur_id, mat_id, doc_id, salon_id, dia, bloque, hi, hf),
        )


# =============================================================================
# TESTS DE TRIGGERS -- sch_celda_validar
# =============================================================================

class TestCeldaValidar:
    """Valida el trigger BEFORE INSERT/UPDATE en `celdas`."""

    def test_celda_valida_se_inserta(self, db_conn, seed):
        """Una celda que cumple todas las reglas debe insertarse sin error."""
        cur = db_conn.cursor()
        _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                      seed["doc_id"], seed["salon_id"], 1, 1)
        # No commit — todo se revierte con rollback al final del test

    def test_dia_no_laborable_se_rechaza(self, db_conn, seed):
        """Dia sabado (6) no esta en dias_laborables -> excepcion."""
        cur = db_conn.cursor()
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                          seed["doc_id"], seed["salon_id"], 6, 1)
        assert "no est" in str(exc.value).lower()
        assert "d" in str(exc.value).lower() and "laborables" in str(exc.value).lower()

    def test_hora_fuera_de_jornada_se_rechaza(self, db_conn, seed):
        """Clase 13:00-14:00 excede el cierre (13:00) -> excepcion."""
        cur = db_conn.cursor()
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                          seed["doc_id"], seed["salon_id"], 1, 7,
                          "13:00:00", "14:00:00")
        assert "fuera de la jornada" in str(exc.value)

    def test_docente_no_dicta_materia_se_rechaza(self, db_conn, seed):
        """El docente no esta asignado a materia_id=2 -> excepcion."""
        cur = db_conn.cursor()
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            _insert_celda(cur, seed["hor_id"], seed["cur_id"], 2,
                          seed["doc_id"], seed["salon_id"], 2, 1)
        assert "no est" in str(exc.value).lower()
        assert "designado para dictar" in str(exc.value).lower()

    def test_docente_no_asignado_curso_se_rechaza(self, db_conn, seed):
        """El docente no tiene curso_id=2 -> excepcion."""
        cur = db_conn.cursor()
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            _insert_celda(cur, seed["hor_id"], 2, seed["mat_id"],
                          seed["doc_id"], seed["salon_id"], 2, 1)
        assert "no est" in str(exc.value).lower()
        assert "asignado al curso" in str(exc.value).lower()

    def test_salon_incorrecto_se_rechaza(self, db_conn, seed):
        """Materia que requiere laboratorio pero se asigna a aula -> excepcion."""
        cur = db_conn.cursor()
        cur.execute(
            """INSERT INTO materias (nombre, categoria, min_horas, max_horas,
                   requiere_salon, tipo_salon_requerido, no_ultima_hora)
                VALUES (%s, 'basica', 1, 2, true, 'laboratorio', false)
               RETURNING id""",
            (f"TestLab {uuid.uuid4().hex[:8]}",),
        )
        mat_lab = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO docente_materia (docente_id, materia_id) VALUES (%s, %s)",
            (seed["doc_id"], mat_lab),
        )
        # No commit — todo se revierte con rollback al final del test

        with pytest.raises(psycopg.errors.RaiseException) as exc:
            _insert_celda(cur, seed["hor_id"], seed["cur_id"], mat_lab,
                          seed["doc_id"], seed["salon_id"], 3, 1)
        assert "requiere un espacio de tipo" in str(exc.value)

    def test_disponibilidad_fuera_ventana_se_rechaza(self, db_conn, seed):
        """Docente con disponibilidad solo 07:00-08:00 los lunes;
        asignar martes 09:00-10:00 -> excepcion."""
        cur = db_conn.cursor()
        cur.execute(
            """INSERT INTO docentes (nombre, apellido, documento, carga_horaria, activo)
               VALUES ('Test', 'NoDisp T037', %s, 10, true)
               RETURNING id""",
            (f"ND-{uuid.uuid4().hex[:8]}",),
        )
        doc_nd = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO disponibilidades (docente_id, dia, hora_inicio, hora_fin)
               VALUES (%s, 1, '07:00:00', '08:00:00')""",
            (doc_nd,),
        )
        cur.execute(
            "INSERT INTO docente_materia (docente_id, materia_id) VALUES (%s, %s)",
            (doc_nd, seed["mat_id"]),
        )
        cur.execute(
            "INSERT INTO docente_curso (docente_id, curso_id) VALUES (%s, %s)",
            (doc_nd, seed["cur_id"]),
        )
        # No commit — todo se revierte con rollback al final del test

        with pytest.raises(psycopg.errors.RaiseException) as exc:
            _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                          doc_nd, seed["salon_id"], 2, 1,
                          "09:00:00", "10:00:00")
        assert "no tiene disponibilidad" in str(exc.value)

    def test_carga_horaria_excedida_se_rechaza(self, db_conn, seed):
        """Docente con carga=2h (120 min). Insertar 3 celdas de 60 min
        (180 min > 120) -> la tercera debe fallar."""
        cur = db_conn.cursor()
        _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                      seed["doc_id"], seed["salon_id"], 1, 1)
        _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                      seed["doc_id"], seed["salon_id"], 2, 1)
        # No commit — todo se revierte con rollback al final del test

        with pytest.raises(psycopg.errors.RaiseException) as exc:
            _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                          seed["doc_id"], seed["salon_id"], 3, 1)
        assert "supera la carga acad" in str(exc.value).lower()

    def test_no_ultima_hora_se_rechaza(self, db_conn, seed):
        """Materia con no_ultima_hora=true en el ultimo bloque (12:00-13:00)
        -> excepcion."""
        cur = db_conn.cursor()
        cur.execute(
            """INSERT INTO materias (nombre, categoria, min_horas, max_horas,
                   requiere_salon, no_ultima_hora)
                VALUES (%s, 'basica', 1, 2, false, true)
               RETURNING id""",
            (f"TestNoUlt {uuid.uuid4().hex[:8]}",),
        )
        mat_nu = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO docentes (nombre, apellido, documento, carga_horaria, activo)
               VALUES ('Test', 'NoUlt T037', %s, 10, true)
               RETURNING id""",
            (f"NU-{uuid.uuid4().hex[:8]}",),
        )
        doc_nu = cur.fetchone()["id"]
        for dia in range(1, 6):
            cur.execute(
                """INSERT INTO disponibilidades (docente_id, dia, hora_inicio, hora_fin)
                   VALUES (%s, %s, '07:00:00', '13:00:00')""",
                (doc_nu, dia),
            )
        cur.execute(
            "INSERT INTO docente_materia (docente_id, materia_id) VALUES (%s, %s)",
            (doc_nu, mat_nu),
        )
        cur.execute(
            "INSERT INTO docente_curso (docente_id, curso_id) VALUES (%s, %s)",
            (doc_nu, seed["cur_id"]),
        )
        # No commit — todo se revierte con rollback al final del test

        with pytest.raises(psycopg.errors.RaiseException) as exc:
            _insert_celda(cur, seed["hor_id"], seed["cur_id"], mat_nu,
                          doc_nu, seed["salon_id"], 4, 6,
                          "12:00:00", "13:00:00")
        assert "ltima hora" in str(exc.value).lower()


# =============================================================================
# TESTS DE TRIGGERS -- sch_horario_validar
# =============================================================================

class TestHorarioValidar:
    """Valida el trigger BEFORE UPDATE OF estado en `horarios`."""

    def test_completo_con_curso_incompleto_se_rechaza(self, db_conn, seed):
        """Curso tiene horas_semanales=2 (120 min) pero solo 1 celda (60 min)
        -> marcar como completo debe fallar."""
        cur = db_conn.cursor()
        _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                      seed["doc_id"], seed["salon_id"], 1, 1)
        # No commit — todo se revierte con rollback al final del test

        with pytest.raises(psycopg.errors.RaiseException) as exc:
            cur.execute(
                "UPDATE horarios SET estado = 'completo' WHERE id = %s",
                (seed["hor_id"],),
            )
        assert "carga semanal" in str(exc.value).lower()

    def test_completo_valido_se_acepta(self, db_conn, seed):
        """Curso con 2 celdas x 60 min = 120 min = 2h = horas_semanales.
        -> marcar como completo debe pasar."""
        cur = db_conn.cursor()
        # El trigger sch_horario_validar hace LEFT JOIN sobre TODOS los cursos
        # de la BD. Eliminar los demas cursos (CASCADE borra sus celdas/FKs).
        # Se revierte con rollback al final del test.
        cur.execute(
            "DELETE FROM cursos WHERE id != %s",
            (seed["cur_id"],),
        )
        _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                      seed["doc_id"], seed["salon_id"], 1, 1)
        _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                      seed["doc_id"], seed["salon_id"], 2, 1)
        # No commit — todo se revierte con rollback al final del test

        cur.execute(
            "UPDATE horarios SET estado = 'completo' WHERE id = %s RETURNING estado",
            (seed["hor_id"],),
        )
        assert cur.fetchone()["estado"] == "completo"

    def test_borrador_a_parcial_no_valida(self, db_conn, seed):
        """La transicion borrador->parcial NO dispara validacion de completitud."""
        cur = db_conn.cursor()
        cur.execute(
            "UPDATE horarios SET estado = 'parcial' WHERE id = %s RETURNING estado",
            (seed["hor_id"],),
        )
        assert cur.fetchone()["estado"] == "parcial"


# =============================================================================
# TESTS DE CONSTRAINTS UNIQUE (choques)
# =============================================================================

class TestUniqueConstraints:
    """Verifica que los UNIQUE constraints de celdas siguen activos."""

    def test_choque_salon(self, db_conn, seed):
        """Mismo salon, dia, bloque -> unique_violation."""
        cur = db_conn.cursor()
        _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                      seed["doc_id"], seed["salon_id"], 1, 1)
        # No commit — todo se revierte con rollback al final del test

        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                          seed["doc_id"], seed["salon_id"], 1, 1)

    def test_choque_docente(self, db_conn, seed):
        """Mismo docente, dia, bloque (distinto salon) -> unique_violation."""
        cur = db_conn.cursor()
        _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                      seed["doc_id"], seed["salon_id"], 1, 1)
        cur.execute(
            """INSERT INTO salones (nombre, tipo, capacidad, activo)
               VALUES (%s, 'aula', 30, true) RETURNING id""",
            (f"TestAula2 {uuid.uuid4().hex[:8]}",),
        )
        salon2 = cur.fetchone()["id"]
        # No commit — todo se revierte con rollback al final del test

        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                          seed["doc_id"], salon2, 1, 1)

    def test_choque_curso(self, db_conn, seed):
        """Mismo curso, dia, bloque (distinto docente y salon) -> unique_violation."""
        cur = db_conn.cursor()
        _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                      seed["doc_id"], seed["salon_id"], 1, 1)

        cur.execute(
            """INSERT INTO docentes (nombre, apellido, documento, carga_horaria, activo)
               VALUES ('Test', 'ChCurso T037', %s, 10, true)
               RETURNING id""",
            (f"CC-{uuid.uuid4().hex[:8]}",),
        )
        doc2 = cur.fetchone()["id"]
        for dia in range(1, 6):
            cur.execute(
                """INSERT INTO disponibilidades (docente_id, dia, hora_inicio, hora_fin)
                   VALUES (%s, %s, '07:00:00', '13:00:00')""",
                (doc2, dia),
            )
        cur.execute(
            "INSERT INTO docente_materia (docente_id, materia_id) VALUES (%s, %s)",
            (doc2, seed["mat_id"]),
        )
        cur.execute(
            "INSERT INTO docente_curso (docente_id, curso_id) VALUES (%s, %s)",
            (doc2, seed["cur_id"]),
        )
        cur.execute(
            """INSERT INTO salones (nombre, tipo, capacidad, activo)
               VALUES (%s, 'aula', 30, true) RETURNING id""",
            (f"TestAula3 {uuid.uuid4().hex[:8]}",),
        )
        salon3 = cur.fetchone()["id"]
        # No commit — todo se revierte con rollback al final del test

        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_celda(cur, seed["hor_id"], seed["cur_id"], seed["mat_id"],
                          doc2, salon3, 1, 1)


# =============================================================================
# TESTS DE RLS -- aislamiento por usuario
# =============================================================================

class TestRLSAislamiento:
    """Verifica que RLS aisla horarios y celdas por usuario_id.

    Estrategia: crea dos usuarios de prueba en auth.users, inserta
    horarios para cada uno, y luego simula ser cada usuario con
    SET LOCAL role authenticated + request.jwt.claims.
    """

    def _create_test_user(self, cur) -> str:
        """Crea un usuario de prueba en auth.users y devuelve su UUID."""
        uid = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO auth.users (id, instance_id, aud, role, email,
                   email_confirmed_at, raw_app_meta_data, raw_user_meta_data,
                   created_at, updated_at)
               VALUES (%s, '00000000-0000-0000-0000-000000000000',
                       'authenticated', 'authenticated', %s,
                       now(), '{}'::jsonb, '{}'::jsonb,
                       now(), now())""",
            (uid, f"test_{uid[:8]}@t037.test"),
        )
        return uid

    def _create_owned_schedule(self, cur, owner_id: str, suffix: str):
        """Create a schedule and all referenced rows under one account owner."""
        cur.execute(
            """INSERT INTO configs (nombre, tipo_jornada, dias_laborables,
                   hora_inicio, hora_fin, minutos_bloque, activa, user_id)
               VALUES (%s, 'unica', '{1,2,3,4,5}', '07:00', '13:00', 60, false, %s)
               RETURNING id""",
            (f"RLS config {suffix}", owner_id),
        )
        config_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO docentes (nombre, apellido, documento, carga_horaria, activo, user_id)
               VALUES ('RLS', %s, %s, 2, true, %s) RETURNING id""",
            (suffix, f"rls-doc-{suffix}-{uuid.uuid4().hex[:8]}", owner_id),
        )
        docente_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO disponibilidades (docente_id, dia, hora_inicio, hora_fin, user_id)
               VALUES (%s, 1, '07:00', '13:00', %s)""",
            (docente_id, owner_id),
        )
        cur.execute(
            """INSERT INTO materias (nombre, categoria, min_horas, max_horas, user_id)
               VALUES (%s, 'basica', 1, 2, %s) RETURNING id""",
            (f"RLS materia {suffix}", owner_id),
        )
        materia_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO salones (nombre, tipo, capacidad, activo, user_id)
               VALUES (%s, 'aula', 30, true, %s) RETURNING id""",
            (f"RLS salon {suffix}", owner_id),
        )
        salon_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO cursos (nombre, nivel, horas_semanales, user_id)
               VALUES (%s, '1', 2, %s) RETURNING id""",
            (f"RLS curso {suffix}", owner_id),
        )
        curso_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO docente_materia (docente_id, materia_id, user_id) VALUES (%s, %s, %s)",
            (docente_id, materia_id, owner_id),
        )
        cur.execute(
            "INSERT INTO docente_curso (docente_id, curso_id, user_id) VALUES (%s, %s, %s)",
            (docente_id, curso_id, owner_id),
        )
        cur.execute(
            """INSERT INTO horarios (configuracion_id, nombre, estado, user_id, usuario_id)
               VALUES (%s, %s, 'borrador', %s, %s) RETURNING id""",
            (config_id, f"RLS schedule {suffix}", owner_id, owner_id),
        )
        return {
            "config_id": config_id,
            "docente_id": docente_id,
            "materia_id": materia_id,
            "salon_id": salon_id,
            "curso_id": curso_id,
            "horario_id": cur.fetchone()["id"],
        }

    def _set_admin(self, cur, user_id: str) -> None:
        cur.execute("UPDATE public.perfiles SET role = 'admin' WHERE id = %s", (user_id,))

    def _set_authenticated(self, cur, user_id: str):
        """Simula ser un usuario autenticado para las siguientes consultas."""
        claims = json.dumps({"sub": user_id, "role": "authenticated"})
        cur.execute("SET LOCAL role authenticated")
        # SET LOCAL no soporta param binding (%s); claims es JSON controlado
        cur.execute("SET LOCAL request.jwt.claims = '{}'".format(claims))

    def _reset_role(self, cur):
        """Vuelve a service_role (postgres) para limpieza."""
        cur.execute("SET LOCAL role postgres")

    def test_horarios_usuario_a_ve_solo_sus_horarios(self, db_conn, seed):
        """Usuario A solo puede ver horarios donde usuario_id = su UID."""
        cur = db_conn.cursor()

        uid_a = self._create_test_user(cur)
        uid_b = self._create_test_user(cur)

        self._create_owned_schedule(cur, uid_a, f"{uid_a[:8]}-A")
        self._create_owned_schedule(cur, uid_b, f"{uid_b[:8]}-B")
        # No commit — todo se revierte con rollback al final del test

        self._set_authenticated(cur, uid_a)
        cur.execute("SELECT count(*) AS n FROM horarios")
        count = cur.fetchone()["n"]
        assert count == 1, f"Usuario A deberia ver 1 horario, vio {count}"

        self._reset_role(cur)
        # No commit — todo se revierte con rollback al final del test

    def test_horarios_usuario_b_ve_solo_sus_horarios(self, db_conn, seed):
        """Usuario B solo puede ver horarios donde usuario_id = su UID."""
        cur = db_conn.cursor()

        uid_a = self._create_test_user(cur)
        uid_b = self._create_test_user(cur)

        self._create_owned_schedule(cur, uid_a, f"{uid_a[:8]}-A")
        self._create_owned_schedule(cur, uid_b, f"{uid_b[:8]}-B")
        # No commit — todo se revierte con rollback al final del test

        self._set_authenticated(cur, uid_b)
        cur.execute("SELECT count(*) AS n FROM horarios")
        count = cur.fetchone()["n"]
        assert count == 1, f"Usuario B deberia ver 1 horario, vio {count}"

        self._reset_role(cur)
        # No commit — todo se revierte con rollback al final del test

    def test_catalogos_estan_aislados_por_usuario(self, db_conn, seed):
        """Owners stay isolated while admin retains global CRUD and child integrity."""
        cur = db_conn.cursor()
        uid_a = self._create_test_user(cur)
        uid_b = self._create_test_user(cur)
        admin_id = self._create_test_user(cur)
        self._set_admin(cur, admin_id)
        owner_rows = {}

        for owner_id, suffix in ((uid_a, "A"), (uid_b, "B")):
            cur.execute(
                """INSERT INTO configs (nombre, tipo_jornada, hora_inicio, hora_fin, user_id)
                   VALUES (%s, 'unica', '07:00', '13:00', %s) RETURNING id""",
                (f"RLS config {suffix}", owner_id),
            )
            config_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO docentes (nombre, apellido, documento, carga_horaria, user_id)
                   VALUES ('RLS', %s, %s, 4, %s) RETURNING id""",
                (suffix, f"rls-doc-{suffix}-{uuid.uuid4().hex[:8]}", owner_id),
            )
            docente_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO cursos (nombre, nivel, horas_semanales, user_id)
                   VALUES (%s, '1', 2, %s) RETURNING id""",
                (f"RLS curso {suffix}", owner_id),
            )
            curso_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO materias (nombre, categoria, min_horas, max_horas, user_id)
                   VALUES (%s, 'basica', 1, 2, %s) RETURNING id""",
                (f"RLS materia {suffix}", owner_id),
            )
            materia_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO salones (nombre, tipo, user_id)
                   VALUES (%s, 'aula', %s) RETURNING id""",
                (f"RLS salon {suffix}", owner_id),
            )
            salon_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO disponibilidades (docente_id, dia, hora_inicio, hora_fin, user_id)
                   VALUES (%s, 1, '07:00', '08:00', %s)""",
                (docente_id, owner_id),
            )
            cur.execute(
                """INSERT INTO docente_materia (docente_id, materia_id, user_id)
                   VALUES (%s, %s, %s)""",
                (docente_id, materia_id, owner_id),
            )
            cur.execute(
                """INSERT INTO docente_curso (docente_id, curso_id, user_id)
                   VALUES (%s, %s, %s)""",
                (docente_id, curso_id, owner_id),
            )
            owner_rows[owner_id] = {
                "config_id": config_id,
                "docente_id": docente_id,
                "curso_id": curso_id,
                "materia_id": materia_id,
                "salon_id": salon_id,
            }

        cur.execute(
            """INSERT INTO horarios (configuracion_id, nombre, estado, user_id, usuario_id)
               VALUES (%s, 'RLS owner A schedule', 'borrador', %s, %s) RETURNING id""",
            (owner_rows[uid_a]["config_id"], uid_a, uid_a),
        )
        schedule_a_id = cur.fetchone()["id"]

        table_names = (
            "configs", "docentes", "cursos", "materias", "salones",
            "disponibilidades", "docente_materia", "docente_curso",
        )
        self._set_authenticated(cur, uid_a)
        for table_name in table_names:
            cur.execute(
                f"SELECT count(*) AS n FROM public.{table_name} WHERE user_id IN (%s, %s)",
                (uid_a, uid_b),
            )
            assert cur.fetchone()["n"] == 1, f"{table_name} exposed another account's row"

        self._reset_role(cur)
        self._set_authenticated(cur, admin_id)
        for table_name in table_names:
            cur.execute(
                f"SELECT count(*) AS n FROM public.{table_name} WHERE user_id IN (%s, %s)",
                (uid_a, uid_b),
            )
            assert cur.fetchone()["n"] == 2, f"admin cannot view both {table_name} owners"

        cur.execute("UPDATE docentes SET telefono = 'admin-edit' WHERE apellido = 'B'")
        assert cur.rowcount == 1

        cur.execute(
            """INSERT INTO cursos (nombre, nivel, horas_semanales, user_id)
               VALUES ('Admin-owned catalog row', '1', 2, %s)""",
            (admin_id,),
        )
        assert cur.rowcount == 1, "admin could not create an actor-owned catalog row"

        cur.execute("SAVEPOINT sp_admin_cross_owner_assignment")
        with pytest.raises(psycopg.errors.RaiseException, match="docente_materia materia owner"):
            cur.execute(
                """INSERT INTO docente_materia (docente_id, materia_id, user_id)
                   VALUES (%s, %s, %s)""",
                (owner_rows[uid_a]["docente_id"], owner_rows[uid_b]["materia_id"], uid_a),
            )
        cur.execute("ROLLBACK TO SAVEPOINT sp_admin_cross_owner_assignment")

        cur.execute("SAVEPOINT sp_admin_cross_owner_course_assignment")
        with pytest.raises(psycopg.errors.RaiseException, match="docente_curso curso owner"):
            cur.execute(
                """INSERT INTO docente_curso (docente_id, curso_id, user_id)
                   VALUES (%s, %s, %s)""",
                (owner_rows[uid_a]["docente_id"], owner_rows[uid_b]["curso_id"], uid_a),
            )
        cur.execute("ROLLBACK TO SAVEPOINT sp_admin_cross_owner_course_assignment")

        cur.execute("SAVEPOINT sp_admin_cross_owner_cell")
        with pytest.raises(psycopg.errors.RaiseException, match="celdas salon owner"):
            cur.execute(
                """INSERT INTO celdas (horario_id, user_id, curso_id, materia_id, docente_id,
                       salon_id, dia, bloque, hora_inicio, hora_fin, bloqueada)
                   VALUES (%s, %s, %s, %s, %s, %s, 1, 1, '07:00', '08:00', false)""",
                (
                    schedule_a_id,
                    uid_a,
                    owner_rows[uid_a]["curso_id"],
                    owner_rows[uid_a]["materia_id"],
                    owner_rows[uid_a]["docente_id"],
                    # A's cell cannot attach B's salon, even for admin.
                    owner_rows[uid_b]["salon_id"],
                ),
            )
        cur.execute("ROLLBACK TO SAVEPOINT sp_admin_cross_owner_cell")

        cur.execute("DELETE FROM salones WHERE nombre = 'RLS salon B'")
        assert cur.rowcount == 1, "admin could not delete another owner's row"

        cur.execute("SAVEPOINT sp_owner_transfer")
        with pytest.raises(psycopg.errors.RaiseException, match="ownership cannot be changed"):
            cur.execute("UPDATE docentes SET user_id = %s WHERE apellido = 'A'", (admin_id,))
        cur.execute("ROLLBACK TO SAVEPOINT sp_owner_transfer")

        self._reset_role(cur)

    def test_celdas_aisladas_por_usuario(self, db_conn, seed):
        """Usuario A no puede ver celdas del horario de usuario B."""
        cur = db_conn.cursor()

        uid_a = self._create_test_user(cur)
        uid_b = self._create_test_user(cur)

        tenant_a = self._create_owned_schedule(cur, uid_a, f"{uid_a[:8]}-A")
        tenant_b = self._create_owned_schedule(cur, uid_b, f"{uid_b[:8]}-B")
        _insert_celda(cur, tenant_a["horario_id"], tenant_a["curso_id"],
                      tenant_a["materia_id"], tenant_a["docente_id"],
                      tenant_a["salon_id"], 1, 1, owner_id=uid_a)
        _insert_celda(cur, tenant_b["horario_id"], tenant_b["curso_id"],
                      tenant_b["materia_id"], tenant_b["docente_id"],
                      tenant_b["salon_id"], 1, 1, owner_id=uid_b)
        # No commit — todo se revierte con rollback al final del test

        self._set_authenticated(cur, uid_a)
        cur.execute("SELECT count(*) AS n FROM celdas")
        count = cur.fetchone()["n"]
        assert count == 1, f"Usuario A deberia ver 1 celda, vio {count}"

        self._reset_role(cur)
        # No commit — todo se revierte con rollback al final del test

    def test_usuario_no_puede_insertar_horario_de_otro(self, db_conn, seed):
        """Usuario A no puede crear un horario con usuario_id de B."""
        cur = db_conn.cursor()
        uid_a = self._create_test_user(cur)
        uid_b = self._create_test_user(cur)
        cur.execute(
            """INSERT INTO configs (nombre, tipo_jornada, hora_inicio, hora_fin, user_id)
               VALUES (%s, 'unica', '07:00', '13:00', %s) RETURNING id""",
            (f"Fraud target config {uuid.uuid4().hex[:8]}", uid_b),
        )
        config_b_id = cur.fetchone()["id"]
        # No commit — todo se revierte con rollback al final del test

        self._set_authenticated(cur, uid_a)
        cur.execute("SAVEPOINT sp_fraude")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                """INSERT INTO horarios (configuracion_id, nombre, estado, user_id, usuario_id)
                   VALUES (%s, %s, 'borrador', %s, %s)""",
                (config_b_id, f"Fraude {uuid.uuid4().hex[:8]}", uid_b, uid_b),
            )
        cur.execute("ROLLBACK TO SAVEPOINT sp_fraude")

        self._reset_role(cur)
        # No commit — todo se revierte con rollback al final del test


# =============================================================================
# TESTS DE EXISTENCIA (regresion estructural)
# =============================================================================

class TestEstructuraBD:
    """Verifica que triggers, funciones y politicas RLS existen."""

    def test_trigger_celdas_validar_existe(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            """SELECT EXISTS (
                   SELECT 1 FROM pg_trigger
                   WHERE tgname = 'trg_celdas_validar'
                     AND NOT tgisinternal
               ) AS exists"""
        )
        assert cur.fetchone()["exists"] is True

    def test_trigger_horarios_validar_existe(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            """SELECT EXISTS (
                   SELECT 1 FROM pg_trigger
                   WHERE tgname = 'trg_horarios_validar'
                     AND NOT tgisinternal
               ) AS exists"""
        )
        assert cur.fetchone()["exists"] is True

    def test_funcion_sch_celda_validar_existe(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            """SELECT EXISTS (
                   SELECT 1 FROM pg_proc WHERE proname = 'sch_celda_validar'
               ) AS exists"""
        )
        assert cur.fetchone()["exists"] is True

    def test_funcion_sch_horario_validar_existe(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            """SELECT EXISTS (
                   SELECT 1 FROM pg_proc WHERE proname = 'sch_horario_validar'
               ) AS exists"""
        )
        assert cur.fetchone()["exists"] is True

    def test_rls_activado_en_horarios(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            """SELECT relrowsecurity AS rls
               FROM pg_class WHERE relname = 'horarios'"""
        )
        assert cur.fetchone()["rls"] is True

    def test_rls_activado_en_celdas(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            """SELECT relrowsecurity AS rls
               FROM pg_class WHERE relname = 'celdas'"""
        )
        assert cur.fetchone()["rls"] is True

    def test_politicas_horarios_existen(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            """SELECT count(*) AS n FROM pg_policies
               WHERE tablename = 'horarios' AND schemaname = 'public'"""
        )
        assert cur.fetchone()["n"] >= 4

    def test_politicas_celdas_existen(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            """SELECT count(*) AS n FROM pg_policies
               WHERE tablename = 'celdas' AND schemaname = 'public'"""
        )
        assert cur.fetchone()["n"] >= 1

    def test_politicas_catalogos_existen(self, db_conn):
        """Every standalone catalog has owner-scoped SELECT/INSERT/UPDATE/DELETE policies."""
        cur = db_conn.cursor()
        cur.execute(
            """SELECT count(DISTINCT tablename) AS n
               FROM pg_policies
               WHERE schemaname = 'public'
                 AND policyname LIKE '%_owner_select'"""
        )
        assert cur.fetchone()["n"] >= 5
