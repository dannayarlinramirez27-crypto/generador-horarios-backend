"""Utilidades compartidas por los routers CRUD.

Centraliza:
  - El mapeo de excepciones de psycopg/Postgres a respuestas HTTP claras
    (400 bad request · 409 conflict · 500/503 servidor), usado después por el
    exception handler global de `app/main.py`.
  - La construcción de sentencias UPDATE parciales (solo campos recibidos).
"""

import psycopg
from fastapi import HTTPException, status


def db_error_to_response(exc: Exception) -> tuple[int, str]:
    """Convierte una excepción de base de datos en (http_status, detail)."""
    if isinstance(exc, psycopg.errors.UniqueViolation):
        return (
            status.HTTP_409_CONFLICT,
            "Ya existe un registro con esos valores (constraint de unicidad).",
        )
    if isinstance(exc, psycopg.errors.ForeignKeyViolation):
        return (
            status.HTTP_409_CONFLICT,
            "El registro está referenciado por otros datos y no puede modificarse/eliminarse.",
        )
    # Errores lanzados por nuestros triggers (sch_celda_validar, sch_horario_validar):
    # se muestran como 400 con el mensaje del propio trigger.
    if isinstance(exc, psycopg.errors.RaiseException):
        return status.HTTP_400_BAD_REQUEST, _first_line(str(exc))
    if isinstance(exc, psycopg.errors.CheckViolation):
        return status.HTTP_400_BAD_REQUEST, "El valor no cumple las restricciones del esquema."
    if isinstance(exc, psycopg.errors.NotNullViolation):
        return status.HTTP_400_BAD_REQUEST, "Falta un valor obligatorio."
    if isinstance(exc, psycopg.OperationalError):
        return status.HTTP_503_SERVICE_UNAVAILABLE, "No se pudo conectar con la base de datos."
    if isinstance(exc, psycopg.Error):
        return status.HTTP_500_INTERNAL_SERVER_ERROR, "Error inesperado de la base de datos."
    return status.HTTP_500_INTERNAL_SERVER_ERROR, "Error interno del servidor."


def raise_db_error(exc: Exception) -> None:
    """Eleva un HTTPException a partir de un error de psycopg/Postgres."""
    http_status, detail = db_error_to_response(exc)
    raise HTTPException(status_code=http_status, detail=detail) from exc


def build_update_statement(
    table: str, pk_column: str, pk_value: int, updates: dict
) -> tuple[str, list]:
    """Arma un UPDATE parcial `SET c1=%s, c2=%s ... WHERE pk=%s RETURNING *`.

    `updates` viene de `model_dump(exclude_unset=True)` del modelo Update, por lo
    que sus claves son nombres de columna validados por el propio esquema.
    """
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se recibieron campos para actualizar.",
        )
    assignments = ", ".join(f"{col} = %s" for col in updates)
    sql = f"UPDATE {table} SET {assignments} WHERE {pk_column} = %s RETURNING *"
    params = [*updates.values(), pk_value]
    return sql, params


def _first_line(text: str) -> str:
    line = text.splitlines()[0]
    return line.replace("ERROR:  ", "").replace("ERROR: ", "").strip()