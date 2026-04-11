from __future__ import annotations

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import with_db_cursor, query_db
from app.core.home_snapshot_cache import bump_home_snapshot_version
from app.core.tenancy import current_tenant_id

router = APIRouter()

# =============================================================================
# Budget Groups (shared allocations) — Postgres
# =============================================================================

class BudgetGroupUpsert(BaseModel):
    year: int
    month: int
    name: str
    allocated: float = 0.0
    cap: Optional[float] = None
    categories: List[str] = []

def _ensure_budget_groups_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS budget_groups (
              id SERIAL PRIMARY KEY,
              year INT NOT NULL,
              month INT NOT NULL,
              name TEXT NOT NULL,
              name_norm TEXT NOT NULL,
              allocated DOUBLE PRECISION NOT NULL DEFAULT 0,
              cap DOUBLE PRECISION NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        cur.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname='public'
                  AND indexname='ux_budget_groups_month_name'
              ) THEN
                CREATE UNIQUE INDEX ux_budget_groups_month_name
                  ON budget_groups(year, month, name_norm);
              END IF;
            END $$;
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS budget_group_categories (
              id SERIAL PRIMARY KEY,
              group_id INT NOT NULL REFERENCES budget_groups(id) ON DELETE CASCADE,
              year INT NOT NULL,
              month INT NOT NULL,
              category TEXT NOT NULL,
              category_norm TEXT NOT NULL
            );
            """
        )
        cur.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname='public'
                  AND indexname='ux_budget_group_categories_unique'
              ) THEN
                CREATE UNIQUE INDEX ux_budget_group_categories_unique
                  ON budget_group_categories(year, month, category_norm);
              END IF;
            END $$;
            """
        )
        conn.commit()

def _norm_name(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

def _norm_cat(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

def _row_first_id(row):
    # Works for tuple rows or dict rows (RealDictCursor)
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get("id") or next(iter(row.values()), None)
    return row[0]

def _month_serial(year: int, month: int) -> int:
    return (int(year) * 100) + int(month)

def _copy_latest_groups_into_month(year: int, month: int) -> bool:
    """
    If requested month has no rows yet, clone the most recent earlier month's
    budget groups + category mappings so monthly budgets carry forward.
    """
    y = int(year)
    m = int(month)
    ym = _month_serial(y, m)

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT 1
            FROM budget_groups
            WHERE year = %s AND month = %s
            LIMIT 1
            """,
            (y, m),
        )
        if cur.fetchone():
            return False

        cur.execute(
            """
            SELECT year, month
            FROM budget_groups
            WHERE ((year * 100) + month) < %s
            ORDER BY year DESC, month DESC
            LIMIT 1
            """,
            (ym,),
        )
        src = cur.fetchone()
        if not src:
            return False

        src_y = int(src.get("year"))
        src_m = int(src.get("month"))
        cur.execute(
            """
            SELECT id, name, name_norm, allocated, cap
            FROM budget_groups
            WHERE year = %s AND month = %s
            ORDER BY name_norm ASC
            """,
            (src_y, src_m),
        )
        src_groups = list(cur.fetchall() or [])
        if not src_groups:
            return False

        id_map: dict[int, int] = {}
        for g in src_groups:
            g_name_norm = g.get("name_norm") or _norm_name(g.get("name") or "")
            cur.execute(
                """
                INSERT INTO budget_groups(
                  year, month, name, name_norm, allocated, cap, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, now(), now())
                ON CONFLICT (year, month, name_norm) DO NOTHING
                RETURNING id
                """,
                (
                    y,
                    m,
                    g.get("name") or "",
                    g_name_norm,
                    float(g.get("allocated") or 0.0),
                    (None if g.get("cap") is None else float(g.get("cap"))),
                ),
            )
            new_id = _row_first_id(cur.fetchone())
            if new_id is None:
                cur.execute(
                    """
                    SELECT id
                    FROM budget_groups
                    WHERE year = %s AND month = %s AND name_norm = %s
                    LIMIT 1
                    """,
                    (y, m, g_name_norm),
                )
                new_id = _row_first_id(cur.fetchone())
            if new_id is not None:
                id_map[int(g.get("id"))] = int(new_id)

        cur.execute(
            """
            SELECT group_id, category, category_norm
            FROM budget_group_categories
            WHERE year = %s AND month = %s
            ORDER BY id ASC
            """,
            (src_y, src_m),
        )
        src_cats = list(cur.fetchall() or [])
        for c in src_cats:
            src_gid = int(c.get("group_id") or 0)
            new_gid = id_map.get(src_gid)
            if not new_gid:
                continue
            cat = _norm_cat(c.get("category") or "")
            if not cat:
                continue
            cur.execute(
                """
                INSERT INTO budget_group_categories(group_id, year, month, category, category_norm)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (int(new_gid), y, m, cat, cat),
            )

        conn.commit()
        return True

def _get_budget_groups_for_month(year: int, month: int) -> list[dict]:
    _ensure_budget_groups_pg()
    _copy_latest_groups_into_month(year, month)
    rows = query_db(
        """
        SELECT
          g.id,
          g.name,
          g.allocated::double precision AS allocated,
          g.cap::double precision AS cap,
          COALESCE(array_agg(c.category ORDER BY c.category) FILTER (WHERE c.category IS NOT NULL), '{}') AS categories
        FROM budget_groups g
        LEFT JOIN budget_group_categories c ON c.group_id = g.id
        WHERE g.year=%s AND g.month=%s
        GROUP BY g.id
        ORDER BY g.name_norm ASC
        """,
        (year, month),
    )

    out = []
    for r in rows:
        cats = r.get("categories") or []
        # psycopg2 might return array as list already; keep safe:
        if isinstance(cats, str):
            cats = [x.strip() for x in cats.strip("{}").split(",") if x.strip()]
        out.append(
            {
                "id": int(r["id"]),
                "name": r.get("name") or "",
                "allocated": float(r.get("allocated") or 0.0),
                "cap": None if r.get("cap") is None else float(r.get("cap")),
                "categories": cats,
            }
        )
    return out

@router.get("/budget/groups")
def get_budget_groups(year: int, month: int):
    return {"ok": True, "groups": _get_budget_groups_for_month(year, month)}

@router.post("/budget/groups")
def upsert_budget_group(b: BudgetGroupUpsert):
    _ensure_budget_groups_pg()

    y = int(b.year)
    m = int(b.month)
    nm = (b.name or "").strip()
    if not nm:
        raise HTTPException(status_code=422, detail="name is required")

    name_norm = _norm_name(nm)
    allocated = float(b.allocated or 0.0)
    cap = None if b.cap is None else float(b.cap)

    cats_in = b.categories or []
    cats_norm = []
    cats_out = []
    for c in cats_in:
        nn = _norm_cat(c)
        if not nn:
            continue
        cats_norm.append(nn)
        cats_out.append(nn)

    with with_db_cursor() as (conn, cur):
        # Upsert group
        cur.execute(
            """
            INSERT INTO budget_groups(year, month, name, name_norm, allocated, cap, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (year, month, name_norm)
            DO UPDATE SET
              name = EXCLUDED.name,
              allocated = EXCLUDED.allocated,
              cap = EXCLUDED.cap,
              updated_at = now()
            RETURNING id
            """,
            (y, m, nm, name_norm, allocated, cap),
        )
        row = cur.fetchone()
        group_id = _row_first_id(row)  # ✅ fixes KeyError: 0
        if group_id is None:
            conn.rollback()
            raise HTTPException(status_code=500, detail="Failed to upsert budget group (no id returned)")

        group_id = int(group_id)

        # Replace categories for this group
        cur.execute("DELETE FROM budget_group_categories WHERE group_id=%s", (group_id,))

        # Ensure a category can belong to only one group per month:
        # delete any existing mapping for these categories in the same (year,month)
        if cats_norm:
            cur.execute(
                """
                DELETE FROM budget_group_categories
                WHERE year=%s AND month=%s AND category_norm = ANY(%s)
                """,
                (y, m, cats_norm),
            )

        for c in cats_out:
            cur.execute(
                """
                INSERT INTO budget_group_categories(group_id, year, month, category, category_norm)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (group_id, y, m, c, c),
            )

        conn.commit()
    bump_home_snapshot_version(current_tenant_id())

    return {"ok": True, "id": group_id}

@router.delete("/budget/groups")
def delete_budget_group(year: int, month: int, name: str):
    _ensure_budget_groups_pg()
    nm = (name or "").strip()
    if not nm:
        raise HTTPException(status_code=422, detail="name is required")

    name_norm = _norm_name(nm)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM budget_groups WHERE year=%s AND month=%s AND name_norm=%s",
            (int(year), int(month), name_norm),
        )
        deleted = (cur.rowcount or 0) > 0
        conn.commit()
    if deleted:
        bump_home_snapshot_version(current_tenant_id())

    return {"ok": True, "deleted": bool(deleted)}
