from contextlib import contextmanager

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover - exercised before dependencies are installed.
    psycopg = None
    dict_row = None


class DatabaseUnavailable(RuntimeError):
    pass


class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url

    @contextmanager
    def connect(self):
        if psycopg is None:
            raise DatabaseUnavailable("The psycopg package is required for PostgreSQL access.")
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            yield conn


def fetch_one(conn, query: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()


def fetch_all(conn, query: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def execute(conn, query: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur
