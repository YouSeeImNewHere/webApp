from __future__ import annotations

from threading import Lock

from db import with_db_cursor

_IGNORE_READY = False
_IGNORE_LOCK = Lock()


def ensure_transactions_ignore_column() -> None:
    global _IGNORE_READY
    if _IGNORE_READY:
        return
    with _IGNORE_LOCK:
        if _IGNORE_READY:
            return
        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                ALTER TABLE transactions
                ADD COLUMN IF NOT EXISTS is_ignored BOOLEAN NOT NULL DEFAULT false
                """
            )
            conn.commit()
        _IGNORE_READY = True
