# db.py
import os
import time
from dotenv import load_dotenv
from contextlib import contextmanager
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# IMPORTANT: open=False so we control lifecycle from FastAPI startup/shutdown
pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=5,
    kwargs={"row_factory": dict_row},
    open=False,
)

def open_pool():
    # Safe to call multiple times
    pool.open()

def close_pool():
    pool.close()

@contextmanager
def get_conn():
    # Assumes pool.open() was called at startup
    with pool.connection() as conn:
        yield conn

def query_db(sql: str, params=()):
    def _run():
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description:
                    return cur.fetchall()
                return []
    return run_db_retry(_run, retries=1)

@contextmanager
def with_db_cursor():
    with get_conn() as conn:
        with conn.cursor() as cur:
            yield conn, cur


def is_transient_db_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return (
        "terminating connection due to administrator command" in s
        or "connection is closed" in s
        or "server closed the connection unexpectedly" in s
        or "could not receive data from server" in s
        or "ssl connection has been closed unexpectedly" in s
    )


def run_db_retry(fn, retries: int = 1, sleep_seconds: float = 0.35):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < retries and is_transient_db_error(e):
                time.sleep(sleep_seconds)
                continue
            raise
    raise last_exc
