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

# Keep defaults conservative for low-traffic apps on Neon:
# - min_size=0 allows full idle scale-down.
# - max_size=4 is enough for a few concurrent users.
DB_POOL_MIN_SIZE = max(0, int(os.getenv("DB_POOL_MIN_SIZE", "0")))
DB_POOL_MAX_SIZE = max(1, int(os.getenv("DB_POOL_MAX_SIZE", "4")))
if DB_POOL_MAX_SIZE < DB_POOL_MIN_SIZE:
    DB_POOL_MAX_SIZE = DB_POOL_MIN_SIZE

DB_POOL_TIMEOUT = max(5, int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "20")))
DB_POOL_MAX_IDLE_SECONDS = max(5, int(os.getenv("DB_POOL_MAX_IDLE_SECONDS", "30")))
DB_POOL_MAX_LIFETIME_SECONDS = max(60, int(os.getenv("DB_POOL_MAX_LIFETIME_SECONDS", "900")))

# IMPORTANT: open=False so we control lifecycle from FastAPI startup/shutdown
pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=DB_POOL_MIN_SIZE,
    max_size=DB_POOL_MAX_SIZE,
    timeout=DB_POOL_TIMEOUT,
    max_idle=DB_POOL_MAX_IDLE_SECONDS,
    max_lifetime=DB_POOL_MAX_LIFETIME_SECONDS,
    kwargs={"row_factory": dict_row},
    open=False,
)


def ensure_performance_indexes():
    """
    Best-effort index creation for high-traffic query paths.
    Safe to call at startup; failures are intentionally non-fatal.
    """
    statements = [
        # Core join/filter paths
        "CREATE INDEX IF NOT EXISTS idx_accounts_tenant_id_id ON accounts (tenant_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_accounts_tenant_type ON accounts (tenant_id, accountType)",
        "CREATE INDEX IF NOT EXISTS idx_startingbalance_tenant_account ON startingbalance (tenant_id, account_id)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_tenant_account ON transactions (tenant_id, account_id)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_tenant_id_id_desc ON transactions (tenant_id, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_tenant_status ON transactions (tenant_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_interest_rates_account_effective ON interest_rates (account_id, effective_date DESC)",
        # Fast exact/group filters commonly used by analytics and rules
        "CREATE INDEX IF NOT EXISTS idx_transactions_tenant_category ON transactions (tenant_id, category)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_tenant_merchant ON transactions (tenant_id, merchant)",
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            for sql in statements:
                try:
                    cur.execute(sql)
                except Exception:
                    conn.rollback()
                else:
                    conn.commit()

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
