"""Trusted request ownership helpers for the direct-Postgres API."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from psycopg.rows import dict_row

from app.auth import _extract_role


def request_role(user: dict[str, Any], conn) -> str:
    """Resolve the role from trusted server-managed sources."""
    role = _extract_role(user, conn)
    if role not in {"admin", "docente"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: se requiere el rol admin o docente.",
        )
    return role


def owner_scope(role: str, user_id: str, column: str = "user_id") -> tuple[str, tuple]:
    """Return a SQL predicate and parameters for the actor's data scope."""
    if role == "admin":
        return "TRUE", ()
    if role != "docente":
        raise HTTPException(status_code=403, detail="Rol no autorizado.")
    return f"{column} = %s", (user_id,)


def fetch_owned_record(
    conn,
    table: str,
    record_id: int,
    role: str,
    user_id: str,
    label: str,
) -> dict:
    predicate, owner_params = owner_scope(role, user_id)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT * FROM {table} WHERE id = %s AND ({predicate})",
            (record_id, *owner_params),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} {record_id} no encontrado.",
        )
    return dict(row)


def referenced_owner(
    conn,
    table: str,
    record_id: int,
    *,
    role: str,
    actor_id: str,
    expected_owner_id: str | None = None,
    label: str = "Registro",
) -> str:
    """Resolve a referenced row and enforce parent-owner consistency.

    Admin can manage independent records across accounts, but a dependent row
    must reference resources owned by its parent account.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT user_id FROM {table} WHERE id = %s", (record_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} {record_id} no encontrado.",
        )
    owner_id = str(row["user_id"])
    if (role != "admin" and owner_id != actor_id) or (
        expected_owner_id is not None and owner_id != expected_owner_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} {record_id} no encontrado.",
        )
    return owner_id


def require_same_owner_references(
    conn,
    references: dict[str, tuple[str, int]],
    *,
    role: str,
    actor_id: str,
    owner_id: str,
) -> None:
    """Validate referenced resources before schedule cells are persisted."""
    for label, (table, record_id) in references.items():
        referenced_owner(
            conn,
            table,
            record_id,
            role=role,
            actor_id=actor_id,
            expected_owner_id=owner_id,
            label=label,
        )
