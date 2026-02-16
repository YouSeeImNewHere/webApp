from __future__ import annotations

import json
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.config import MAX_TRANSFER_WINDOW_DAYS, MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id
from db import with_db_cursor, query_db

router = APIRouter()

# =============================================================================
# Transactions feeds (Postgres)
# =============================================================================
def _require_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")
    return int(tid)

def _is_transfer_like(cat: Optional[str]) -> bool:
    c = (cat or "").strip().lower()
    return c in ("transfer", "card payment")

def _cents(x: float) -> int:
    return int(round(abs(float(x)) * 100))

def attach_transfer_peers_pg(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Adds:
      - transfer_peer: "Institution — Name"
      - transfer_peer_id: int
    for rows whose category is Transfer/Card Payment.

    We do this in Python so we don't need tricky SQL across your mixed date formats.
    """
    if not rows:
        return rows
    tid = _require_tenant_id()

    # Build account display map
    acct_rows = query_db(
        "SELECT id, institution, name FROM accounts" + (" WHERE tenant_id = %s" if tid else ""),
        ((int(tid),) if tid else ()),
    )
    acct_name = {int(a["id"]): f'{a["institution"]} — {a["name"]}' for a in acct_rows}

    # Work only on candidates in the current payload that have dateISO
    cands = []
    for r in rows:
        if not _is_transfer_like(r.get("category")):
            continue
        d = r.get("dateISO")
        if not d:
            continue
        try:
            amt = float(r.get("amount") or 0.0)
        except Exception:
            continue
        if amt == 0:
            continue
        cands.append(
            {
                "id": r.get("id"),
                "account_id": int(r.get("account_id") or 0),
                "date": d if isinstance(d, date) else datetime.fromisoformat(str(d)).date(),
                "cents": _cents(amt),
                "sign": 1 if amt > 0 else -1,
            }
        )

    if not cands:
        return rows

    # Define a wide window to query possible peers just once
    min_d = min(c["date"] for c in cands) - timedelta(days=MAX_TRANSFER_WINDOW_DAYS)
    max_d = max(c["date"] for c in cands) + timedelta(days=MAX_TRANSFER_WINDOW_DAYS)

    peer_rows = query_db(
        f"""
        WITH base AS (
          SELECT
            t.id,
            t.account_id,
            t.amount::double precision AS amount,
            LOWER(TRIM(COALESCE(t.category,''))) AS category,
            COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date
          FROM transactions t
          WHERE LOWER(TRIM(COALESCE(t.category,''))) IN ('transfer','card payment')
            {"AND t.tenant_id = %s" if tid else ""}
        ),
        norm AS (
          SELECT
            *,
            CASE
              WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
              WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
              ELSE NULL
            END AS d
          FROM base
        )
        SELECT id, account_id, amount, category, d
        FROM norm
        WHERE d IS NOT NULL AND d BETWEEN %s AND %s
        """,
        ((int(tid), min_d, max_d) if tid else (min_d, max_d)),
    )

    peers = []
    for p in peer_rows:
        try:
            amt = float(p["amount"] or 0.0)
        except Exception:
            continue
        if amt == 0:
            continue
        peers.append(
            {
                "id": p["id"],
                "account_id": int(p["account_id"]),
                "date": p["d"],
                "cents": _cents(amt),
                "sign": 1 if amt > 0 else -1,
            }
        )

    # Index peers by (cents, sign) for quick lookup
    by_key: Dict[tuple[int, int], List[dict]] = {}
    for p in peers:
        by_key.setdefault((p["cents"], p["sign"]), []).append(p)
    for k in by_key:
        by_key[k].sort(key=lambda x: (x["date"], str(x["id"])))

    used_peer_ids = set()
    id_to_peer = {}

    for c in cands:
        opp = by_key.get((c["cents"], -c["sign"]), [])
        best = None
        best_score = None

        for o in opp:
            if o["id"] in used_peer_ids:
                continue
            if o["account_id"] == c["account_id"]:
                continue
            dd = abs((o["date"] - c["date"]).days)
            if dd > MAX_TRANSFER_WINDOW_DAYS:
                continue
            score = (dd, str(o["id"]))
            if best_score is None or score < best_score:
                best_score = score
                best = o

        if best:
            used_peer_ids.add(best["id"])
            id_to_peer[c["id"]] = (best["account_id"], acct_name.get(best["account_id"]))

    for r in rows:
        pid = id_to_peer.get(r.get("id"))
        if pid:
            peer_id, peer_label = pid
            r["transfer_peer_id"] = int(peer_id)
            r["transfer_peer"] = peer_label or f"Account {peer_id}"

    return rows

class TxCategoryUpdate(BaseModel):
    category: str = ""


class TxMetaUpdate(BaseModel):
    status: Optional[str] = None
    postedDate: Optional[str] = None


def _normalize_status(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s:
        return "posted"
    if s not in {"pending", "posted"}:
        raise HTTPException(status_code=400, detail={"ok": False, "error": "invalid_status"})
    return s


def _normalize_posted_date(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() == "unknown":
        return "unknown"
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d.strftime("%m/%d/%Y")
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail={"ok": False, "error": "invalid_postedDate"})


@router.post("/transaction/{tx_id}/category")
def transaction_set_category(tx_id: str, body: TxCategoryUpdate):
    category = (body.category or "").strip()
    tid = _require_tenant_id()

    with with_db_cursor() as (conn, cur):
        if tid:
            cur.execute(
                """
                UPDATE transactions
                SET category = %s
                WHERE id = %s AND tenant_id = %s
                """,
                (category, tx_id, int(tid)),
            )
        else:
            cur.execute(
                """
                UPDATE transactions
                SET category = %s
                WHERE id = %s
                """,
                (category, tx_id),
            )
        if (cur.rowcount or 0) == 0:
            conn.rollback()
            raise HTTPException(status_code=404, detail={"ok": False, "error": "not_found", "id": tx_id})

        conn.commit()

    return {"ok": True, "id": tx_id, "category": category}


@router.patch("/transaction/{tx_id}/meta")
def transaction_update_meta(tx_id: str, body: TxMetaUpdate):
    next_status = _normalize_status(body.status)
    next_posted = _normalize_posted_date(body.postedDate)
    if next_status is None and next_posted is None:
        raise HTTPException(status_code=400, detail={"ok": False, "error": "no_fields"})

    tid = _require_tenant_id()
    set_parts: List[str] = []
    vals: List[Any] = []
    if next_status is not None:
        set_parts.append("status = %s")
        vals.append(next_status)
    if next_posted is not None:
        set_parts.append("postedDate = %s")
        vals.append(next_posted)

    where_sql = "WHERE id = %s"
    vals.append(tx_id)
    if tid:
        where_sql += " AND tenant_id = %s"
        vals.append(int(tid))

    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"""
            UPDATE transactions
            SET {", ".join(set_parts)}
            {where_sql}
            """,
            tuple(vals),
        )
        if (cur.rowcount or 0) == 0:
            conn.rollback()
            raise HTTPException(status_code=404, detail={"ok": False, "error": "not_found", "id": tx_id})
        conn.commit()

    return {
        "ok": True,
        "id": tx_id,
        "status": next_status,
        "postedDate": next_posted,
    }

@router.delete("/transaction/{tx_id}")
def transaction_delete(tx_id: str):
    """
    Permanently deletes a transaction by id.
    """
    tid = _require_tenant_id()
    with with_db_cursor() as (conn, cur):
        try:
            if tid:
                cur.execute("DELETE FROM transactions WHERE id = %s AND tenant_id = %s", (tx_id, int(tid)))
            else:
                cur.execute("DELETE FROM transactions WHERE id = %s", (tx_id,))
            if (cur.rowcount or 0) == 0:
                conn.rollback()
                raise HTTPException(
                    status_code=404,
                    detail={"ok": False, "error": "not_found", "id": tx_id},
                )
            conn.commit()
            return {"ok": True, "deleted": tx_id}
        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
