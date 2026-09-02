from urllib.parse import urlparse

from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.config import get_settings

# Descompone la DATABASE_URL en parámetros explícitos para evitar que
# psycopg (o el pooler) tenga que parsear query strings en la URI.
# Esto evita problemas con prepared statements y parámetros extra en la URL.
_url = urlparse(get_settings().database_url_value)

# Pool de conexiones a Postgres/Supabase.
# - `open=False` → el pool NO se conecta al importar la app: la primera
#   conexión se abre bajo demanda, a la primera consulta real. Esto permite
#   que `/api/v1/health` responda sin que la BD esté disponible.
# - Cada request toma una conexión del pool y la devuelve al terminar
#   (dependency `get_db`).
pool = ConnectionPool(
    host=_url.hostname,
    port=_url.port,
    user=_url.username,
    password=_url.password,
    dbname=_url.path.lstrip('/'),
    sslmode='require',
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
    with pool.connection() as conn:
        yield conn