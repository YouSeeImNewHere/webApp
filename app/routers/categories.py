from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from db import with_db_cursor, query_db
from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id

router = APIRouter()

# =============================================================================
# Categories endpoints (Postgres) — ported from categories.py
# =============================================================================

def _require_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)


def get_category_from_db_pg(tx_ids: List[int]) -> Optional[str]:
    """
    Postgres version of categories.py:get_category_from_db(tx_ids)
    Returns the first non-empty category found among tx_ids (or None).
    """
    if not tx_ids:
        return None
    tid = _require_tenant_id()

    # NOTE: use = ANY(%s) to pass a python list safely as a Postgres array
    rows = query_db(
        f"""
        SELECT category
        FROM transactions
        WHERE id = ANY(%s)
          {"AND tenant_id = %s" if tid else ""}
          AND category IS NOT NULL
          AND TRIM(category) <> ''
        LIMIT 1
        """,
        ((tx_ids, int(tid)) if tid else (tx_ids,)),
    )
    return rows[0]["category"] if rows else None

@router.get("/categories")
def list_categories():
    """
    Union of:
      - distinct categories present in transactions
      - distinct categories present in CategoryRules
    """
    tid = _require_tenant_id()
    rows = query_db(
        f"""
        SELECT category FROM (
          SELECT DISTINCT TRIM(category) AS category
          FROM transactions
          WHERE category IS NOT NULL AND TRIM(category) <> ''
            {"AND tenant_id = %s" if tid else ""}

          UNION

          SELECT DISTINCT TRIM(category) AS category
          FROM "categoryrules"
          WHERE category IS NOT NULL AND TRIM(category) <> ''
            {"AND tenant_id = %s" if tid else ""}
        ) u
        ORDER BY LOWER(category) ASC
        """,
        ((int(tid), int(tid)) if tid else ()),
    )
    return [r["category"] for r in rows]
