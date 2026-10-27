import psycopg
from fastapi import HTTPException, status
from psycopg import Connection
from psycopg_pool import ConnectionPool, PoolTimeout

from app.config import get_settings

# Pool de conexiones a Postgres/Supabase.
# - `open=False` → el pool NO se conecta al importar la app: la primera
#   conexión se abre bajo demanda, a la primera consulta real. Esto permite
#   que `/api/v1/health` responda sin que la BD esté disponible.
# - Cada request toma una conexión del pool y la devuelve al terminar
#   (dependency `get_db`).
pool = ConnectionPool(
    conninfo=get_settings().database_url_value,
    min_size=1,
    max_size=10,
    kwargs={"autocommit": True},
)


def get_db() -> Connection:
    """Dependency de FastAPI que entrega una conexión transaccional.

    Se usa como `def endpoint(conn: Annotated[Connection, Depends(get_db)])`.
    psycopg v3 NO gestiona transacciones implícitas; entonces se trabaja en
    modo `autocommit` y cada operación confirma de inmediato (caso CRUD simple).
    """
    try:
        with pool.connection() as conn:
            yield conn
    except (psycopg.Error, PoolTimeout) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de datos no está disponible temporalmente. Inténtalo de nuevo.",
        ) from exc
