from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import MULTI_TENANT_ENABLED, OWNER_GOOGLE_EMAIL
from db import with_db_cursor, query_db

router = APIRouter()

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TenantPurgeBody(BaseModel):
    dry_run: bool = False
    delete_tenant: bool = True
    delete_users: bool = True


def _is_owner_request(request: Request) -> bool:
    if not MULTI_TENANT_ENABLED:
        return True
    session_email = (request.session.get("google_email") or "").strip().lower()
    owner_email = (OWNER_GOOGLE_EMAIL or "").strip().lower()
    return bool(owner_email) and session_email == owner_email


def _require_owner(request: Request) -> None:
    if not bool(request.session.get("authed")):
        raise HTTPException(status_code=401, detail="unauthorized")
    if not _is_owner_request(request):
        raise HTTPException(status_code=403, detail="forbidden")


def _table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS t", (f"public.{table}",))
    row = cur.fetchone() or {}
    return bool(row.get("t"))


def _tenant_tables_with_column() -> list[str]:
    rows = query_db(
        """
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND column_name = 'tenant_id'
        ORDER BY table_name ASC
        """
    )
    out: list[str] = []
    for r in rows:
        t = str(r.get("table_name") or "").strip()
        if t and _IDENT_RE.match(t):
            out.append(t)
    return out


def _delete_order_for_tables(tables: list[str]) -> list[str]:
    preferred = [
        "transaction_receipts",
        "startingbalance",
        "interest_rates",
        "notified_transactions",
        "transactions",
        "accounts",
        "budget_group_categories",
        "budget_group_member",
        "budget_group_month",
        "budget_groups",
        "budget_category_month",
        "sinking_fund_ledger",
        "sinking_fund",
        "receipts",
        "app_settings",
        "ui_layout",
        "les_profile",
        "categoryrules",
        "daily_limit_snapshot",
        "email_seen_ids",
        "notifications",
        "merchant_aliases",
        "recurring_ignore_patterns",
        "recurring_ignore_merchants",
        "recurring_ignore_categories",
        "recurring_cadence_overrides",
        "pushover_pending",
        "card_benefits",
        "card_benefits_legacy",
        "csv_mapping_presets",
        "email_parser_trial_samples",
        "email_parser_trial_drafts",
        "home_snapshot_month_budget",
        "home_snapshot_page_home",
        "home_snapshot_state",
        "widget_refresh_state",
        "tenant_onboarding",
        "users",
    ]
    rank = {name: i for i, name in enumerate(preferred)}
    return sorted(tables, key=lambda t: (rank.get(t, 10_000), t))


def _tenant_footprint(tenant_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _tenant_tables_with_column():
        rows = query_db(f'SELECT COUNT(*)::int AS n FROM "{table}" WHERE tenant_id = %s', (int(tenant_id),))
        counts[table] = int((rows[0] or {}).get("n") or 0) if rows else 0
    return counts


@router.get("/admin/tenants")
def admin_tenants(request: Request):
    _require_owner(request)
    rows = query_db(
        """
        SELECT
          t.id,
          t.slug,
          t.name,
          t.status,
          t.created_at,
          (SELECT COUNT(*)::int FROM users u WHERE u.tenant_id = t.id) AS users_count,
          (SELECT COUNT(*)::int FROM accounts a WHERE a.tenant_id = t.id) AS accounts_count,
          (SELECT COUNT(*)::int FROM transactions x WHERE x.tenant_id = t.id) AS transactions_count
        FROM tenants t
        ORDER BY t.id ASC
        """
    )
    items = [dict(r) for r in (rows or [])]
    for i in items:
        i["is_owner_workspace"] = str(i.get("slug") or "").strip().lower() == "owner"
    return {"ok": True, "items": items}


@router.get("/admin/tenants/{tenant_id}/footprint")
def admin_tenant_footprint(tenant_id: int, request: Request):
    _require_owner(request)
    rows = query_db("SELECT id, slug, name, status FROM tenants WHERE id = %s LIMIT 1", (int(tenant_id),))
    if not rows:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    tenant = dict(rows[0])
    return {"ok": True, "tenant": tenant, "counts": _tenant_footprint(int(tenant_id))}


@router.post("/admin/tenants/{tenant_id}/purge")
def admin_tenant_purge(tenant_id: int, request: Request, body: TenantPurgeBody):
    _require_owner(request)
    tid = int(tenant_id)
    rows = query_db("SELECT id, slug, name, status FROM tenants WHERE id = %s LIMIT 1", (tid,))
    if not rows:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    tenant = dict(rows[0])
    if str(tenant.get("slug") or "").strip().lower() == "owner":
        raise HTTPException(status_code=400, detail="owner_tenant_cannot_be_purged")

    if bool(body.delete_tenant) and not bool(body.delete_users):
        raise HTTPException(status_code=422, detail="delete_users must be true when delete_tenant is true")

    preview_counts = _tenant_footprint(tid)
    if bool(body.dry_run):
        return {
            "ok": True,
            "dry_run": True,
            "tenant": tenant,
            "counts": preview_counts,
        }

    tables = _delete_order_for_tables(_tenant_tables_with_column())
    deleted: dict[str, int] = {}
    with with_db_cursor() as (conn, cur):
        for table in tables:
            if table == "users" and not bool(body.delete_users):
                continue
            if not _table_exists(cur, table):
                continue
            cur.execute(f'DELETE FROM "{table}" WHERE tenant_id = %s', (tid,))
            deleted[table] = int(cur.rowcount or 0)

        if bool(body.delete_tenant):
            cur.execute("DELETE FROM tenant_onboarding WHERE tenant_id = %s", (tid,))
            deleted["tenant_onboarding"] = deleted.get("tenant_onboarding", 0) + int(cur.rowcount or 0)
            cur.execute("DELETE FROM tenants WHERE id = %s", (tid,))
            deleted["tenants"] = int(cur.rowcount or 0)

        conn.commit()

    return {
        "ok": True,
        "dry_run": False,
        "tenant": tenant,
        "deleted": deleted,
    }
