from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from db import with_db_cursor, query_db

router = APIRouter()

# =============================================================================
# Categories endpoints (Postgres) — ported from categories.py
# =============================================================================

def get_category_from_db_pg(tx_ids: List[int]) -> Optional[str]:
    """
    Postgres version of categories.py:get_category_from_db(tx_ids)
    Returns the first non-empty category found among tx_ids (or None).
    """
    if not tx_ids:
        return None

    # NOTE: use = ANY(%s) to pass a python list safely as a Postgres array
    rows = query_db(
        """
        SELECT category
        FROM transactions
        WHERE id = ANY(%s)
          AND category IS NOT NULL
          AND TRIM(category) <> ''
        LIMIT 1
        """,
        (tx_ids,),
    )
    return rows[0]["category"] if rows else None

@router.get("/categories")
def list_categories():
    """
    Union of:
      - distinct categories present in transactions
      - distinct categories present in CategoryRules
    """
    rows = query_db(
        """
        SELECT category FROM (
          SELECT DISTINCT TRIM(category) AS category
          FROM transactions
          WHERE category IS NOT NULL AND TRIM(category) <> ''

          UNION

          SELECT DISTINCT TRIM(category) AS category
          FROM "categoryrules"
          WHERE category IS NOT NULL AND TRIM(category) <> ''
        ) u
        ORDER BY LOWER(category) ASC
        """
    )
    return [r["category"] for r in rows]

