"""Focused unit coverage for backend account ownership enforcement."""

import pytest
from fastapi import HTTPException
from datetime import time
from contextlib import nullcontext

from app.models.configs import ConfigCreate
from app.models.cursos import CursoCreate
from app.models.docentes import DocenteCreate, DocenteUpdate
from app.models.materias import MateriaCreate
from app.models.salones import SalonCreate
from app.models.asignaciones import DocenteMateriaCreate
from app.ownership import (
    fetch_owned_record,
    owner_scope,
    referenced_owner,
    require_same_owner_references,
)
from app.routers import asignaciones, configs, cursos, docentes, horarios, materias, salones
from app.scheduler.loader import _scope_clause

OWNER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


class _Cursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.calls.append((sql, params))

    def fetchone(self):
        if self.conn.ones is not None:
            return self.conn.ones.pop(0)
        return self.conn.one

    def fetchall(self):
        return self.conn.many

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _Connection:
    def __init__(self, *, one=None, ones=None, many=None):
        self.one = one
        self.ones = list(ones) if ones is not None else None
        self.many = many or []
        self.calls = []

    def cursor(self, row_factory=None):
        return _Cursor(self)

    def transaction(self):
        return nullcontext()


def test_docente_create_uses_verified_subject_and_ignores_client_owner():
    conn = _Connection(one={"id": 5, "user_id": OWNER})
    payload = DocenteCreate(
        nombre="Ada",
        apellido="Lovelace",
        documento="A-5",
        carga_horaria=10,
        user_id=OTHER,
    )

    docentes.create_docente(payload, conn, {"sub": OWNER, "app_metadata": {"role": "docente"}})

    sql, params = conn.calls[0]
    assert "user_id" in sql
    assert params[-1] == OWNER
    assert "user_id" not in payload.model_dump()


@pytest.mark.parametrize(
    ("create", "payload"),
    [
        (configs.create_config, ConfigCreate(tipo_jornada="unica", hora_inicio=time(7), hora_fin=time(13), user_id=OTHER)),
        (cursos.create_curso, CursoCreate(nombre="Uno", nivel="1", horas_semanales=2, user_id=OTHER)),
        (materias.create_materia, MateriaCreate(nombre="Ciencia", categoria="basica", user_id=OTHER)),
        (salones.create_salon, SalonCreate(nombre="Aula", tipo="aula", user_id=OTHER)),
    ],
)
def test_all_standalone_create_routes_explicitly_insert_verified_owner(create, payload):
    conn = _Connection(one={"id": 1, "user_id": OWNER})

    create(payload, conn, {"sub": OWNER, "app_metadata": {"role": "docente"}})

    sql, params = conn.calls[-1]
    assert "user_id" in sql
    assert params[-1] == OWNER


@pytest.mark.parametrize(
    ("role", "expected_sql", "expected_params"),
    [
        ("docente", "user_id = %s", (OWNER,)),
        ("admin", "TRUE", ()),
    ],
)
def test_owner_scope_is_account_scoped_for_docentes_and_global_for_admin(
    role, expected_sql, expected_params
):
    assert owner_scope(role, OWNER) == (expected_sql, expected_params)


def test_list_docentes_applies_verified_owner_filter():
    conn = _Connection()

    docentes.list_docentes(conn=conn, usuario={"sub": OWNER, "app_metadata": {"role": "docente"}})

    sql, params = conn.calls[0]
    assert "user_id = %s" in sql
    assert params == [OWNER]


def test_admin_docente_list_remains_global():
    conn = _Connection()

    docentes.list_docentes(conn=conn, usuario={"sub": OWNER, "app_metadata": {"role": "admin"}})

    sql, params = conn.calls[0]
    assert "WHERE TRUE" in sql
    assert params == []


def test_admin_can_fetch_another_owners_record():
    conn = _Connection(one={"id": 9, "user_id": OTHER})

    row = fetch_owned_record(conn, "materias", 9, "admin", OWNER, "Materia")

    assert row["user_id"] == OTHER
    assert "WHERE id = %s AND (TRUE)" in conn.calls[0][0]
    assert conn.calls[0][1] == (9,)


def test_admin_assignment_cannot_reference_resource_outside_parent_owner():
    conn = _Connection(ones=[{"id": 3, "user_id": OWNER}, {"user_id": OTHER}])

    with pytest.raises(HTTPException) as exc:
        asignaciones.assign_materia_a_docente(
            DocenteMateriaCreate(docente_id=3, materia_id=7),
            conn,
            {"sub": "admin-id", "app_metadata": {"role": "admin"}},
        )

    assert exc.value.status_code == 404
    assert len(conn.calls) == 2
    assert "INSERT INTO docente_materia" not in " ".join(call[0] for call in conn.calls)


def test_ordinary_user_cannot_reference_another_accounts_record():
    conn = _Connection(one={"user_id": OTHER})

    with pytest.raises(HTTPException) as exc:
        referenced_owner(
            conn,
            "materias",
            9,
            role="docente",
            actor_id=OWNER,
            expected_owner_id=OWNER,
            label="Materia",
        )

    assert exc.value.status_code == 404
    assert conn.calls[0][1] == (9,)


def test_admin_dependent_references_must_match_parent_owner():
    conn = _Connection(one={"user_id": OTHER})

    with pytest.raises(HTTPException) as exc:
        referenced_owner(
            conn,
            "cursos",
            11,
            role="admin",
            actor_id="admin-id",
            expected_owner_id=OWNER,
            label="Curso",
        )

    assert exc.value.status_code == 404
    assert conn.calls[0][1] == (11,)


def test_admin_schedule_cell_references_must_match_schedule_owner():
    conn = _Connection(one={"user_id": OTHER})

    with pytest.raises(HTTPException) as exc:
        require_same_owner_references(
            conn,
            {"Materia": ("materias", 7)},
            role="admin",
            actor_id="admin-id",
            owner_id=OWNER,
        )

    assert exc.value.status_code == 404
    assert conn.calls[0][1] == (7,)


@pytest.mark.parametrize(
    ("owner_id", "admin", "expected_sql", "expected_params"),
    [
        (OWNER, True, "user_id = %s", (OWNER,)),
        (OWNER, False, "user_id = %s", (OWNER,)),
        (None, True, "TRUE", ()),
    ],
)
def test_scheduler_scope_respects_explicit_owner_for_admin(
    owner_id, admin, expected_sql, expected_params
):
    assert _scope_clause(owner_id, admin) == (expected_sql, expected_params)


def test_active_config_is_contextual_even_for_admin():
    conn = _Connection(one={"id": 4, "user_id": OWNER, "activa": True})

    configs.get_active_config(
        conn,
        {"sub": OWNER, "app_metadata": {"role": "admin"}},
    )

    sql, params = conn.calls[0]
    assert "WHERE activa = true AND (user_id = %s)" in sql
    assert params == (OWNER,)


def test_admin_configs_list_remains_global():
    conn = _Connection(many=[{"id": 1, "user_id": OWNER}, {"id": 2, "user_id": OTHER}])

    rows = configs.list_configs(
        conn,
        {"sub": "admin-id", "app_metadata": {"role": "admin"}},
    )

    assert len(rows) == 2
    assert "WHERE TRUE" in conn.calls[0][0]


def test_update_models_cannot_transfer_row_ownership():
    update = DocenteUpdate(nombre="Grace", user_id=OTHER)

    assert update.model_dump(exclude_unset=True) == {"nombre": "Grace"}


def test_schedule_insert_sets_canonical_and_legacy_owner_from_actor():
    conn = _Connection(one={"id": 3, "user_id": OWNER, "usuario_id": OWNER})

    horarios._insert_horario(conn, 1, "Owned", "borrador", OWNER)

    sql, params = conn.calls[0]
    assert "user_id, usuario_id" in sql
    assert params[-2:] == (OWNER, OWNER)
