"""Focused tests for trusted role resolution and docente authorization."""

from inspect import getclosurevars

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.auth import (
    ROLES_VALIDOS,
    _extract_role,
    _extract_role_from_claims,
    ensure_role_allowed,
)
from app.routers import (
    asignaciones,
    configs,
    cursos,
    docentes,
    horarios,
    materias,
    salones,
)
from app.routers.horarios import READ_ROLES, _load_horario

MODULE_ROUTERS = (
    configs.router,
    docentes.router,
    asignaciones.router,
    cursos.router,
    materias.router,
    salones.router,
    horarios.router,
)


class _ProfileCursor:
    def __init__(self, row):
        self.row = row
        self.params = None

    def execute(self, _sql, params):
        self.params = params

    def fetchone(self):
        return self.row

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _ProfileConnection:
    def __init__(self, row):
        self.cursor_instance = _ProfileCursor(row)

    def cursor(self, row_factory=None):
        return self.cursor_instance


class _ScheduleCursor:
    def __init__(self):
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return {"id": 42, "usuario_id": "owner-1"}

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _ScheduleConnection:
    def __init__(self):
        self.cursor_instance = _ScheduleCursor()

    def cursor(self, row_factory=None):
        return self.cursor_instance


def test_user_metadata_cannot_grant_a_role():
    assert _extract_role_from_claims({"user_metadata": {"role": "admin"}}) == "desconocido"


def test_user_metadata_resolves_signup_docente_role():
    assert _extract_role_from_claims({"user_metadata": {"role": "docente"}}) == "docente"


def test_signup_docente_role_is_resolved_for_current_user():
    claims = {"sub": "teacher-1", "user_metadata": {"role": "docente"}}
    assert _extract_role(claims) == "docente"


def test_user_metadata_admin_does_not_grant_admin_to_current_user():
    claims = {
        "sub": "user-1",
        "email": "member@school.edu",
        "user_metadata": {"role": "admin"},
    }
    assert _extract_role(claims) == "desconocido"


@pytest.mark.parametrize("role", ["admin", "docente"])
def test_server_managed_role_claim_is_recognized(role):
    assert _extract_role_from_claims({"app_metadata": {"role": role}}) == role


def test_unknown_role_claims_fail_closed():
    assert _extract_role_from_claims({"app_metadata": {"role": "visitor"}}) == "desconocido"


def test_only_admin_and_docente_are_valid_roles():
    assert ROLES_VALIDOS == {"admin", "docente"}


def test_database_profile_role_precedes_app_metadata():
    claims = {"sub": "user-1", "app_metadata": {"role": "admin"}}
    assert _extract_role(claims, _ProfileConnection({"rol": "docente"})) == "docente"


def test_invalid_database_profile_falls_back_to_server_managed_role():
    claims = {"sub": "user-1", "app_metadata": {"role": "docente"}}
    assert _extract_role(claims, _ProfileConnection({"rol": "visitor"})) == "docente"


@pytest.mark.parametrize("role", ["admin", "docente"])
def test_all_roles_can_read_and_validate_schedules(role):
    ensure_role_allowed(role, READ_ROLES)


def _role_guards(dependant):
    guards = []
    for dependency in dependant.dependencies:
        call = dependency.call
        if getattr(call, "__name__", None) == "_check_role":
            allowed_roles = getclosurevars(call).nonlocals["allowed_roles"]
            guards.append(allowed_roles)
        guards.extend(_role_guards(dependency))
    return guards


@pytest.mark.parametrize("role", ["admin", "docente"])
def test_both_roles_can_use_every_module_endpoint(role):
    for router in MODULE_ROUTERS:
        endpoints = [route for route in router.routes if isinstance(route, APIRoute)]
        assert endpoints, f"{router.prefix} should expose module endpoints"
        for endpoint in endpoints:
            guards = _role_guards(endpoint.dependant)
            assert guards, f"{endpoint.path} has no role guard"
            assert all({"admin", "docente"}.issubset(guard) for guard in guards), (
                f"{role} must be permitted for {endpoint.path}"
            )
            for guard in guards:
                ensure_role_allowed(role, guard)


def test_unknown_role_cannot_use_any_module_endpoint():
    for router in MODULE_ROUTERS:
        for endpoint in router.routes:
            if not isinstance(endpoint, APIRoute):
                continue
            for guard in _role_guards(endpoint.dependant):
                with pytest.raises(HTTPException) as exc:
                    ensure_role_allowed("desconocido", guard)
                assert exc.value.status_code == 403


def test_admin_can_read_shared_schedules():
    conn = _ScheduleConnection()
    _load_horario(conn, horario_id=42, usuario_id="reader-1", role="admin")
    assert "usuario_id =" not in conn.cursor_instance.sql
    assert conn.cursor_instance.params == (42,)


def test_docente_schedule_reads_remain_scoped_to_their_own_records():
    conn = _ScheduleConnection()
    _load_horario(conn, horario_id=42, usuario_id="teacher-1", role="docente")
    assert "usuario_id = %s" in conn.cursor_instance.sql
    assert conn.cursor_instance.params == (42, "teacher-1")


def test_unknown_role_cannot_load_schedules():
    with pytest.raises(HTTPException) as exc:
        _load_horario(
            _ScheduleConnection(),
            horario_id=42,
            usuario_id="user-1",
            role="desconocido",
        )
    assert exc.value.status_code == 403
