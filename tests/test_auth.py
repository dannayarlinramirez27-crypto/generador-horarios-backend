"""Focused tests for trusted role resolution and docente authorization."""

import pytest
from fastapi import HTTPException

from app.auth import (
    _extract_docente_id_from_email,
    _extract_role,
    _extract_role_from_claims,
    ensure_docente_access,
    ensure_role_allowed,
)
from app.routers.horarios import READ_ROLES, _load_horario


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


class _DocenteCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _DocenteConnection:
    def __init__(self, rows):
        self.cursor_instance = _DocenteCursor(rows)

    def cursor(self):
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


def test_database_profile_role_precedes_app_metadata():
    claims = {"sub": "user-1", "app_metadata": {"role": "admin"}}
    assert _extract_role(claims, _ProfileConnection({"rol": "docente"})) == "docente"


def test_invalid_database_profile_falls_back_to_server_managed_role():
    claims = {"sub": "user-1", "app_metadata": {"role": "docente"}}
    assert _extract_role(claims, _ProfileConnection({"rol": "visitor"})) == "docente"


@pytest.mark.parametrize("role", ["admin", "docente"])
def test_all_roles_can_read_and_validate_schedules(role):
    ensure_role_allowed(role, READ_ROLES)


@pytest.mark.parametrize(
    ("role", "allowed", "permitted"),
    [
        ("admin", ["admin"], True),
        ("docente", ["admin", "docente"], True),
        ("desconocido", ["admin", "docente"], False),
        ("docente", ["admin"], False),
    ],
)
def test_role_authorization_matrix(role, allowed, permitted):
    if permitted:
        ensure_role_allowed(role, allowed)
    else:
        with pytest.raises(HTTPException) as exc:
            ensure_role_allowed(role, allowed)
        assert exc.value.status_code == 403


def test_admin_can_manage_any_docente_availability():
    ensure_docente_access("admin", requested_docente_id=42, linked_docente_id=None)


def test_docente_can_manage_only_the_email_linked_record():
    ensure_docente_access("docente", requested_docente_id=42, linked_docente_id=42)
    with pytest.raises(HTTPException) as exc:
        ensure_docente_access("docente", requested_docente_id=43, linked_docente_id=42)
    assert exc.value.status_code == 403


def test_unlinked_docente_is_denied_with_clear_error():
    with pytest.raises(HTTPException) as exc:
        ensure_docente_access("docente", requested_docente_id=42, linked_docente_id=None)
    assert exc.value.status_code == 403
    assert "no está vinculada" in exc.value.detail


def test_unknown_role_cannot_manage_docente_availability():
    with pytest.raises(HTTPException) as exc:
        ensure_docente_access("desconocido", requested_docente_id=42, linked_docente_id=42)
    assert exc.value.status_code == 403


def test_email_lookup_is_case_insensitive_and_requires_a_unique_match():
    conn = _DocenteConnection([{"id": 42}])
    assert _extract_docente_id_from_email(conn, "Teacher@school.edu") == 42
    assert "LOWER(email) = LOWER(%s)" in conn.cursor_instance.sql
    assert conn.cursor_instance.params == ("Teacher@school.edu",)
    assert _extract_docente_id_from_email(_DocenteConnection([]), "teacher@school.edu") is None
    assert _extract_docente_id_from_email(
        _DocenteConnection([{"id": 42}, {"id": 43}]), "teacher@school.edu"
    ) is None


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
