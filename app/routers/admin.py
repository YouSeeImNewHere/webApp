from __future__ import annotations

import os
import re
from typing import Any

import requests as _requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import MULTI_TENANT_ENABLED, OWNER_GOOGLE_EMAIL
from app.core.admin_error_events import (
    list_admin_error_events,
    clear_admin_error_events,
    log_admin_error_event,
)
from app.core.email_parse_events import (
    list_email_parse_events,
    clear_email_parse_events,
)
from app.core.tenancy import current_tenant_id
from db import with_db_cursor, query_db

router = APIRouter()

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TenantPurgeBody(BaseModel):
    dry_run: bool = False
    delete_tenant: bool = True
    delete_users: bool = True


class ClientErrorBody(BaseModel):
    source: str | None = None
    message: str | None = None
    stack: str | None = None
    page_url: str | None = None
    route: str | None = None
    request_url: str | None = None
    request_method: str | None = None
    status_code: int | None = None
    user_agent: str | None = None


class EmailParseEventsClearBody(BaseModel):
    tenant_id: int | None = None
    user_email: str | None = None


def _is_mobile_authed(request: Request) -> bool:
    return bool(getattr(request.state, "mobile_authed", False))


def _is_owner_request(request: Request) -> bool:
    preview_header = str(request.headers.get("x-non-admin-preview") or "").strip().lower()
    if preview_header in {"1", "true", "yes", "on"}:
        return False
    if not MULTI_TENANT_ENABLED:
        return True
    # Accept email from mobile token or browser session
    state_email = str(getattr(request.state, "google_email", "") or "").strip().lower()
    session_email = (request.session.get("google_email") or "").strip().lower()
    effective_email = state_email or session_email
    owner_email = (OWNER_GOOGLE_EMAIL or "").strip().lower()
    return bool(owner_email) and effective_email == owner_email


def _require_owner(request: Request) -> None:
    if not bool(request.session.get("authed")) and not _is_mobile_authed(request):
        raise HTTPException(status_code=401, detail="unauthorized")
    if not _is_owner_request(request):
        raise HTTPException(status_code=403, detail="forbidden")


def _require_authed(request: Request) -> None:
    if not bool(request.session.get("authed")) and not _is_mobile_authed(request):
        raise HTTPException(status_code=401, detail="unauthorized")


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


@router.get("/admin/error-notifications")
def admin_error_notifications(request: Request, limit: int = 200):
    _require_owner(request)
    rows = list_admin_error_events(limit=int(limit))
    items: list[dict[str, Any]] = []
    for r in rows:
        items.append(
            {
                "id": int(r.get("id") or 0),
                "created_at": (r["created_at"].isoformat() if r.get("created_at") else None),
                "tenant_id": (int(r["tenant_id"]) if r.get("tenant_id") is not None else None),
                "user_email": r.get("user_email"),
                "method": r.get("method"),
                "path": r.get("path"),
                "query_string": r.get("query_string"),
                "page_url": r.get("page_url"),
                "referer": r.get("referer"),
                "request_id": r.get("request_id"),
                "status_code": int(r.get("status_code") or 0),
                "error_message": r.get("error_message"),
                "client_ip": r.get("client_ip"),
                "user_agent": r.get("user_agent"),
            }
        )
    return {"ok": True, "items": items}


@router.post("/admin/error-notifications/clear")
def admin_error_notifications_clear(request: Request):
    _require_owner(request)
    deleted = clear_admin_error_events()
    return {"ok": True, "deleted": int(deleted)}


@router.get("/admin/email-parse-events")
def admin_email_parse_events(
    request: Request,
    limit: int = 200,
    tenant_id: int | None = None,
    user_email: str | None = None,
):
    _require_owner(request)
    rows = list_email_parse_events(
        limit=int(limit),
        tenant_id=(int(tenant_id) if tenant_id is not None else None),
        user_email=(str(user_email or "").strip().lower() or None),
    )
    items: list[dict[str, Any]] = []
    for r in rows:
        items.append(
            {
                "id": int(r.get("id") or 0),
                "created_at": (r["created_at"].isoformat() if r.get("created_at") else None),
                "tenant_id": (int(r["tenant_id"]) if r.get("tenant_id") is not None else None),
                "user_email": r.get("user_email"),
                "run_source": r.get("run_source"),
                "imap_id": r.get("imap_id"),
                "sender": r.get("sender"),
                "subject": r.get("subject"),
                "received_at": r.get("received_at"),
                "matched": bool(r.get("matched")),
                "status": r.get("status"),
                "reason": r.get("reason"),
                "inserted": bool(r.get("inserted")),
                "notified": bool(r.get("notified")),
                "parser_draft_id": (int(r["parser_draft_id"]) if r.get("parser_draft_id") is not None else None),
                "parser_slot": r.get("parser_slot"),
                "account_id": (int(r["account_id"]) if r.get("account_id") is not None else None),
                "account_label": r.get("account_label"),
                "amount": (float(r["amount"]) if r.get("amount") is not None else None),
                "merchant": r.get("merchant"),
                "context": (r.get("context_json") if isinstance(r.get("context_json"), dict) else {}),
            }
        )
    return {"ok": True, "items": items}


@router.post("/admin/email-parse-events/clear")
def admin_email_parse_events_clear(request: Request, body: EmailParseEventsClearBody):
    _require_owner(request)
    deleted = clear_email_parse_events(
        tenant_id=(int(body.tenant_id) if body.tenant_id is not None else None),
        user_email=(str(body.user_email or "").strip().lower() or None),
    )
    return {"ok": True, "deleted": int(deleted)}


@router.post("/admin/error-notifications/client")
def admin_error_notifications_client(request: Request, body: ClientErrorBody):
    _require_authed(request)

    path = str(body.request_url or "").strip()
    if path:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(path)
            if parsed.path:
                path = parsed.path
                query_string = (parsed.query or "").strip() or None
            else:
                query_string = None
        except Exception:
            query_string = None
    else:
        path = "/client-error"
        query_string = None

    status_code = int(body.status_code or 0)
    if status_code < 0 or status_code > 999:
        status_code = 0

    message_parts: list[str] = []
    source = str(body.source or "").strip()
    message = str(body.message or "").strip()
    stack = str(body.stack or "").strip()
    route = str(body.route or "").strip()
    if source:
        message_parts.append(f"source={source}")
    if route:
        message_parts.append(f"route={route}")
    if message:
        message_parts.append(message)
    if stack:
        message_parts.append(stack[:2000])
    error_message = "\n".join([p for p in message_parts if p]).strip()[:4000]

    tenant_id = None
    try:
        tid = current_tenant_id()
        tenant_id = int(tid) if tid else None
    except Exception:
        tenant_id = None
    if tenant_id is None:
        try:
            tid_session = request.session.get("tenant_id")
            tenant_id = int(tid_session) if tid_session else None
        except Exception:
            tenant_id = None

    user_email = str(request.session.get("google_email") or "").strip().lower() or None
    client_ip = str((request.client.host if request.client else "") or "")

    log_admin_error_event(
        tenant_id=tenant_id,
        user_email=user_email,
        method=(str(body.request_method or "").strip().upper() or "CLIENT"),
        path=(path or "/client-error"),
        query_string=query_string,
        page_url=(str(body.page_url or "").strip() or request.headers.get("x-client-page-url") or None),
        referer=(request.headers.get("referer") or None),
        request_id=(request.headers.get("x-request-id") or None),
        status_code=status_code,
        error_message=(error_message or "client_error_report"),
        client_ip=(client_ip or None),
        user_agent=(str(body.user_agent or "").strip() or request.headers.get("user-agent") or None),
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Infra metrics  (Render + Neon)
# ---------------------------------------------------------------------------

RENDER_API_KEY = os.getenv("RENDER_API_KEY", "")
NEON_API_KEY   = os.getenv("NEON_API_KEY", "")
NEON_PROJECT_ID = os.getenv("NEON_PROJECT_ID", "")


def _render_get(headers: dict, path: str, **kwargs) -> dict | list | None:
    try:
        r = _requests.get(f"https://api.render.com/v1{path}", headers=headers, timeout=10, **kwargs)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def _render_metrics() -> dict:
    if not RENDER_API_KEY:
        return {"error": "RENDER_API_KEY not configured"}
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}", "Accept": "application/json"}
    try:
        svc_r = _requests.get("https://api.render.com/v1/services?limit=20", headers=headers, timeout=10)
        svc_r.raise_for_status()
        services_raw = svc_r.json()

        services = []
        for item in services_raw:
            svc = item.get("service", item)
            svc_id = svc.get("id", "")
            details = svc.get("serviceDetails", {}) or {}
            svc_type = svc.get("type", "")

            # Latest deploy
            latest_deploy = None
            if svc_id:
                deploys = _render_get(headers, f"/services/{svc_id}/deploys?limit=1")
                if deploys and isinstance(deploys, list) and deploys:
                    d = deploys[0].get("deploy", deploys[0])
                    latest_deploy = {
                        "id": d.get("id"),
                        "status": d.get("status"),
                        "trigger": d.get("trigger"),
                        "finishedAt": d.get("finishedAt"),
                        "commitMessage": (d.get("commit") or {}).get("message"),
                        "commitId": ((d.get("commit") or {}).get("id") or "")[:7] or None,
                    }

            # Disk usage (static sites / services expose this)
            disk = None
            if details.get("disk"):
                disk = {
                    "name": details["disk"].get("name"),
                    "sizeGB": details["disk"].get("sizeGB"),
                    "mountPath": details["disk"].get("mountPath"),
                }

            services.append({
                "id": svc_id,
                "name": svc.get("name"),
                "type": svc_type,
                "suspended": svc.get("suspended", "not_suspended"),
                "serviceDetails": {
                    "env": details.get("env"),
                    "region": details.get("region"),
                    "plan": details.get("plan"),
                    "numInstances": details.get("numInstances"),
                    "healthCheckPath": details.get("healthCheckPath"),
                    "autoDeploy": details.get("autoDeploy"),
                    "disk": disk,
                },
                "latestDeploy": latest_deploy,
                "updatedAt": svc.get("updatedAt"),
                "createdAt": svc.get("createdAt"),
            })

        return {"services": services}
    except _requests.HTTPError as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        return {"error": f"Render API {code or 'error'}"}
    except _requests.exceptions.RequestException as e:
        return {"error": f"Render network error: {type(e).__name__}"}
    except Exception as e:
        return {"error": str(e)}


def _neon_metrics() -> dict:
    if not NEON_API_KEY:
        return {"error": "NEON_API_KEY not configured"}
    headers = {"Authorization": f"Bearer {NEON_API_KEY}", "Accept": "application/json"}
    project_id = NEON_PROJECT_ID
    try:
        if not project_id:
            proj_r = _requests.get(
                "https://console.neon.tech/api/v2/projects",
                headers=headers,
                params={"limit": 10},
                timeout=10,
            )
            if not proj_r.ok:
                body = ""
                try:
                    body = proj_r.json().get("message") or proj_r.text[:200]
                except Exception:
                    body = proj_r.text[:200]
                return {"error": f"Neon API {proj_r.status_code}: {body}"}
            projects = proj_r.json().get("projects", [])
            if projects:
                project_id = projects[0]["id"]
            else:
                return {"error": "No Neon projects found — set NEON_PROJECT_ID"}

        proj_r = _requests.get(f"https://console.neon.tech/api/v2/projects/{project_id}", headers=headers, timeout=10)
        if not proj_r.ok:
            return {"error": f"Neon project {proj_r.status_code}"}
        project = proj_r.json().get("project", {})

        br_r = _requests.get(f"https://console.neon.tech/api/v2/projects/{project_id}/branches", headers=headers, timeout=10)
        if not br_r.ok:
            return {"error": f"Neon branches {br_r.status_code}"}
        branches = [
            {
                "id": b.get("id"),
                "name": b.get("name"),
                "default": b.get("default", False),
                "currentState": b.get("current_state"),
                "logicalSize": b.get("logical_size"),
                "cpuUsedSec": b.get("cpu_used_sec"),
                "updatedAt": b.get("updated_at"),
            }
            for b in br_r.json().get("branches", [])
        ]

        ep_r = _requests.get(f"https://console.neon.tech/api/v2/projects/{project_id}/endpoints", headers=headers, timeout=10)
        if not ep_r.ok:
            return {"error": f"Neon endpoints {ep_r.status_code}"}
        endpoints = [
            {
                "id": e.get("id"),
                "host": e.get("host"),
                "type": e.get("type"),
                "currentState": e.get("current_state"),
                "pendingState": e.get("pending_state"),
                "region": e.get("region_id"),
                "autoscalingLimitMinCu": e.get("autoscaling_limit_min_cu"),
                "autoscalingLimitMaxCu": e.get("autoscaling_limit_max_cu"),
                "suspendTimeoutSeconds": e.get("suspend_timeout_seconds"),
                "updatedAt": e.get("updated_at"),
            }
            for e in ep_r.json().get("endpoints", [])
        ]

        # Recent operations
        ops_r = _requests.get(
            f"https://console.neon.tech/api/v2/projects/{project_id}/operations",
            headers=headers,
            params={"limit": 10},
            timeout=10,
        )
        recent_ops = []
        if ops_r.ok:
            for op in (ops_r.json().get("operations") or []):
                recent_ops.append({
                    "id": op.get("id"),
                    "action": op.get("action"),
                    "status": op.get("status"),
                    "error": op.get("error"),
                    "createdAt": op.get("created_at"),
                    "updatedAt": op.get("updated_at"),
                    "totalDurationMs": op.get("total_duration_ms"),
                })

        # Quota / limits — free-tier projects don't return a quota object,
        # so we build synthetic limits from what the API does expose plus
        # known Neon free-tier caps (free_v3 plan).
        quota = project.get("quota") or {}
        subscription = (project.get("owner") or {}).get("subscription_type", "")
        storage_limit_bytes = project.get("branch_logical_size_limit_bytes")  # e.g. 536870912 = 512 MB
        storage_used_bytes = project.get("synthetic_storage_size")            # actual bytes on disk

        # Known Neon free_v3 monthly caps
        FREE_COMPUTE_SECONDS = 191.9 * 3600   # 191.9 compute-hours
        FREE_ACTIVE_SECONDS  = 5 * 30 * 24 * 3600  # not officially published; use 5-month proxy
        FREE_TRANSFER_BYTES  = 5 * 1024 ** 3  # 5 GB

        def _quota_limit(api_key, free_fallback):
            v = quota.get(api_key)
            if v is not None:
                return v
            if "free" in subscription:
                return free_fallback
            return None

        effective_quota = {
            "computeTimeSeconds": _quota_limit("compute_time_seconds", FREE_COMPUTE_SECONDS),
            "activeTimeSeconds":  _quota_limit("active_time_seconds",  FREE_ACTIVE_SECONDS),
            "dataTransferBytes":  _quota_limit("data_transfer_bytes",  FREE_TRANSFER_BYTES),
            "writtenDataBytes":   quota.get("written_data_bytes"),
            "storageLimitBytes":  storage_limit_bytes,
        }

        default_endpoint_settings = project.get("default_endpoint_settings") or {}

        return {
            "project": {
                "id": project.get("id"),
                "name": project.get("name"),
                "region": project.get("region_id"),
                "pgVersion": project.get("pg_version"),
                "subscriptionType": subscription,
                "cpuUsedSec": project.get("cpu_used_sec"),
                "dataStorageBytesHour": project.get("data_storage_bytes_hour"),
                "storageBytesUsed": storage_used_bytes,
                "dataTransferBytes": project.get("data_transfer_bytes"),
                "writtenDataBytes": project.get("written_data_bytes"),
                "activeTimeSeconds": project.get("active_time_seconds"),
                "computeTimeSeconds": project.get("compute_time_seconds"),
                "createdAt": project.get("created_at"),
                "updatedAt": project.get("updated_at"),
                "quota": effective_quota,
                "defaultEndpointSettings": {
                    "autoscalingLimitMinCu": default_endpoint_settings.get("autoscaling_limit_min_cu"),
                    "autoscalingLimitMaxCu": default_endpoint_settings.get("autoscaling_limit_max_cu"),
                    "suspendTimeoutSeconds": default_endpoint_settings.get("suspend_timeout_seconds"),
                } if default_endpoint_settings else None,
            },
            "branches": branches,
            "endpoints": endpoints,
            "recentOperations": recent_ops,
        }
    except _requests.HTTPError as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        return {"error": f"Neon API {code or 'error'}"}
    except _requests.exceptions.RequestException as e:
        return {"error": f"Neon network error: {type(e).__name__}"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/admin/infra-metrics")
def admin_infra_metrics(request: Request):
    _require_owner(request)
    return {"render": _render_metrics(), "neon": _neon_metrics()}


# ---------------------------------------------------------------------------
# Homelab metrics (Netdata, local to the same host)
# ---------------------------------------------------------------------------

NETDATA_URL = os.getenv("NETDATA_URL", "http://127.0.0.1:19999")


def _netdata_dim_value(chart: dict, dim: str) -> float | None:
    d = (chart.get("dimensions") or {}).get(dim)
    if not d:
        return None
    v = d.get("value")
    return float(v) if v is not None else None


def _homelab_metrics() -> dict:
    try:
        r = _requests.get(f"{NETDATA_URL}/api/v1/allmetrics", params={"format": "json"}, timeout=5)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"error": f"Netdata unreachable: {type(e).__name__}"}

    out: dict[str, Any] = {}

    cpu = data.get("system.cpu")
    if cpu:
        idle = _netdata_dim_value(cpu, "idle") or 0.0
        out["cpuUsedPercent"] = round(max(0.0, 100.0 - idle), 1)

    ram = data.get("system.ram")
    if ram:
        used = _netdata_dim_value(ram, "used") or 0.0
        free = _netdata_dim_value(ram, "free") or 0.0
        cached = _netdata_dim_value(ram, "cached") or 0.0
        buffers = _netdata_dim_value(ram, "buffers") or 0.0
        total = used + free + cached + buffers
        out["ram"] = {
            "usedMB": round(used, 1),
            "totalMB": round(total, 1),
            "usedPercent": round((used / total * 100.0), 1) if total else None,
        }

    root_disk = data.get("disk_space./")
    if root_disk:
        used = _netdata_dim_value(root_disk, "used") or 0.0
        avail = _netdata_dim_value(root_disk, "avail") or 0.0
        total = used + avail
        out["diskRoot"] = {
            "usedGB": round(used, 1),
            "totalGB": round(total, 1),
            "usedPercent": round((used / total * 100.0), 1) if total else None,
        }

    net = data.get("system.net")
    if net:
        out["network"] = {
            "inKbps": _netdata_dim_value(net, "InOctets"),
            "outKbps": _netdata_dim_value(net, "OutOctets"),
            "units": net.get("units"),
        }

    temps = []
    for key, chart in data.items():
        if key.startswith("sensors.temperature_") and key.endswith("_input"):
            val = _netdata_dim_value(chart, "input")
            if val is not None:
                temps.append({"label": chart.get("name") or key, "celsius": round(val, 1)})
    if temps:
        out["temperatures"] = temps

    return out


@router.get("/admin/homelab-metrics")
def admin_homelab_metrics(request: Request):
    _require_owner(request)
    return {"homelab": _homelab_metrics()}
