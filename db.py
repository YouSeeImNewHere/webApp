# db.py
import os
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
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                return cur.fetchall()
            return []

@contextmanager
def with_db_cursor():
    with get_conn() as conn:
        with conn.cursor() as cur:
            yield conn, cur
