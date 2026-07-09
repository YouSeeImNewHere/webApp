from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from app.core.tenancy import current_tenant_id
from app.core.transactions_ignore import ensure_transactions_ignore_column
from app.core.home_snapshot_cache import bump_home_snapshot_version
from db import get_conn

router = APIRouter()


def ensure_financing_tables():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS financing_plans (
                    id SERIAL PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    total_amount DECIMAL(12,2) NOT NULL,
                    monthly_payment DECIMAL(12,2) NOT NULL,
                    total_months INTEGER NOT NULL,
                    months_paid INTEGER NOT NULL DEFAULT 0,
                    start_date DATE NOT NULL DEFAULT CURRENT_DATE,
                    transaction_id TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        conn.commit()


class FinancingPlanIn(BaseModel):
    label: str
    total_amount: float
    total_months: int
    transaction_id: Optional[str] = None


class RecordPaymentIn(BaseModel):
    plan_id: int


def _serialize(row: dict) -> dict:
    # `row` here is already a dict — db.py's pool is configured with
    # row_factory=dict_row, so cur.fetchone()/fetchall() never return plain
    # tuples. Re-zipping against cur.description (as this file used to)
    # zips column names against a dict's keys instead of its values,
    # silently replacing every field with its own column name and blowing
    # up downstream float()/comparison calls with a 500.
    for k in ("start_date", "created_at"):
        v = row.get(k)
        if v and not isinstance(v, str):
            row[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
    return row


@router.get("/financing/plans")
def get_plans():
    tid = current_tenant_id()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, label, total_amount, monthly_payment, total_months,
                       months_paid, start_date, transaction_id, created_at
                FROM financing_plans
                WHERE tenant_id = %s
                ORDER BY created_at DESC
            """, (tid,))
            rows = [_serialize(r) for r in cur.fetchall()]
    # Compute derived fields
    for r in rows:
        r["total_amount"] = float(r["total_amount"])
        r["monthly_payment"] = float(r["monthly_payment"])
        r["months_remaining"] = max(0, r["total_months"] - r["months_paid"])
        r["amount_paid"] = round(float(r["monthly_payment"]) * r["months_paid"], 2)
        r["amount_remaining"] = round(float(r["total_amount"]) - r["amount_paid"], 2)
        r["is_complete"] = r["months_paid"] >= r["total_months"]
    return rows


@router.post("/financing/plans")
def create_plan(body: FinancingPlanIn):
    if body.total_months <= 0:
        raise HTTPException(status_code=400, detail="total_months must be > 0")
    monthly = round(body.total_amount / body.total_months, 2)
    tid = current_tenant_id()
    ensure_transactions_ignore_column()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO financing_plans
                    (tenant_id, label, total_amount, monthly_payment, total_months, transaction_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, label, total_amount, monthly_payment, total_months,
                          months_paid, start_date, transaction_id, created_at
            """, (tid, body.label, body.total_amount, monthly, body.total_months, body.transaction_id))
            row = _serialize(cur.fetchone())
            # The original transaction's full amount already hit "spent so
            # far" the month it posted. Once it's financed, that one-time hit
            # is replaced by the flat monthly installment (see
            # get_active_monthly_financing_total, applied every month
            # start_date <= month, including the month of purchase) — so
            # ignore the original transaction everywhere spend is tallied,
            # or the purchase would be counted twice: once in full, once
            # amortized.
            if body.transaction_id:
                cur.execute(
                    "UPDATE transactions SET is_ignored = true WHERE id = %s AND tenant_id = %s",
                    (body.transaction_id, tid),
                )
        conn.commit()
    bump_home_snapshot_version(tid)
    row["total_amount"] = float(row["total_amount"])
    row["monthly_payment"] = float(row["monthly_payment"])
    row["months_remaining"] = row["total_months"]
    row["amount_paid"] = 0.0
    row["amount_remaining"] = float(row["total_amount"])
    row["is_complete"] = False
    return row


@router.post("/financing/plans/{plan_id}/pay")
def record_payment(plan_id: int):
    tid = current_tenant_id()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE financing_plans
                SET months_paid = LEAST(months_paid + 1, total_months)
                WHERE id = %s AND tenant_id = %s
                RETURNING months_paid, total_months
            """, (plan_id, tid))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Plan not found")
        conn.commit()
    bump_home_snapshot_version(tid)
    return {"months_paid": row["months_paid"], "is_complete": row["months_paid"] >= row["total_months"]}


@router.delete("/financing/plans/{plan_id}")
def delete_plan(plan_id: int):
    tid = current_tenant_id()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT transaction_id FROM financing_plans WHERE id=%s AND tenant_id=%s",
                (plan_id, tid),
            )
            existing = cur.fetchone()
            cur.execute("DELETE FROM financing_plans WHERE id=%s AND tenant_id=%s", (plan_id, tid))
            # Removing the plan un-does the "ignore the original transaction"
            # substitution from create_plan, so the purchase counts as
            # regular spend again.
            if existing and existing.get("transaction_id"):
                cur.execute(
                    "UPDATE transactions SET is_ignored = false WHERE id = %s AND tenant_id = %s",
                    (existing["transaction_id"], tid),
                )
        conn.commit()
    bump_home_snapshot_version(tid)
    return {"ok": True}


def get_active_monthly_financing_total(tid: int, year: int, month: int) -> float:
    """Returns sum of monthly payments for plans active in the given month."""
    check_date = date(year, month, 1)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(monthly_payment), 0)
                FROM financing_plans
                WHERE tenant_id = %s
                  AND months_paid < total_months
                  AND start_date <= %s
            """, (tid, check_date))
            row = cur.fetchone()
    return float(list(row.values())[0]) if row else 0.0
