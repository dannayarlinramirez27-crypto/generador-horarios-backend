from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.config import get_settings

# Pool de conexiones a Postgres/Supabase: cada request toma una conexión del
# pool y la devuelve al terminar (dependency `get_db`).
pool = ConnectionPool(
    conninfo=get_settings().database_url_value,
    min_size=1,
    max_size=10,
)
pool.open()


def get_db() -> Connection:
    with pool.connection() as conn:
        yield conn