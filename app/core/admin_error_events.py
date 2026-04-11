from __future__ import annotations

from typing import Any

from db import with_db_cursor, query_db


def ensure_admin_error_events_table_pg() -> None:
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_error_events (
              id BIGSERIAL PRIMARY KEY,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              tenant_id BIGINT NULL,
              user_email TEXT NULL,
              method TEXT NOT NULL,
              path TEXT NOT NULL,
              query_string TEXT NULL,
              page_url TEXT NULL,
              referer TEXT NULL,
              request_id TEXT NULL,
              status_code INT NOT NULL,
              error_message TEXT NULL,
              client_ip TEXT NULL,
              user_agent TEXT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_admin_error_events_created
            ON admin_error_events(created_at DESC)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_admin_error_events_tenant_created
            ON admin_error_events(tenant_id, created_at DESC)
            """
        )
        conn.commit()


def log_admin_error_event(
    *,
    tenant_id: int | None,
    user_email: str | None,
    method: str,
    path: str,
    query_string: str | None,
    page_url: str | None,
    referer: str | None,
    request_id: str | None,
    status_code: int,
    error_message: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> None:
    ensure_admin_error_events_table_pg()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO admin_error_events (
              tenant_id, user_email, method, path, query_string,
              page_url, referer, request_id, status_code, error_message,
              client_ip, user_agent
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                (int(tenant_id) if tenant_id else None),
                (str(user_email or "").strip().lower() or None),
                str(method or "").strip().upper() or "GET",
                str(path or "").strip() or "/",
                (str(query_string or "").strip() or None),
                (str(page_url or "").strip() or None),
                (str(referer or "").strip() or None),
                (str(request_id or "").strip() or None),
                int(status_code or 500),
                (str(error_message or "").strip() or None),
                (str(client_ip or "").strip() or None),
                (str(user_agent or "").strip() or None),
            ),
        )
        conn.commit()


def list_admin_error_events(*, limit: int = 200) -> list[dict[str, Any]]:
    ensure_admin_error_events_table_pg()
    rows = query_db(
        """
        SELECT
          id,
          created_at,
          tenant_id,
          user_email,
          method,
          path,
          query_string,
          page_url,
          referer,
          request_id,
          status_code,
          error_message,
          client_ip,
          user_agent
        FROM admin_error_events
        ORDER BY id DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 200), 2000)),),
    ) or []
    return [dict(r) for r in rows]


def clear_admin_error_events() -> int:
    ensure_admin_error_events_table_pg()
    with with_db_cursor() as (conn, cur):
        cur.execute("DELETE FROM admin_error_events")
        deleted = int(cur.rowcount or 0)
        conn.commit()
    return deleted
