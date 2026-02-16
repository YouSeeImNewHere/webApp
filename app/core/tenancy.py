from __future__ import annotations

from contextvars import ContextVar
import re

from db import with_db_cursor
from app.core.config import MULTI_TENANT_ENABLED, OWNER_GOOGLE_EMAIL

CORE_TENANT_TABLES = [
    "accounts",
    "transactions",
    "startingbalance",
    "notifications",
    "app_settings",
    "budget_category_month",
    "budget_group_categories",
    "budget_group_member",
    "budget_group_month",
    "budget_groups",
    "card_benefits",
    "card_benefits_legacy",
    "categoryrules",
    "daily_limit_snapshot",
    "email_seen_ids",
    "interest_rates",
    "les_profile",
    "merchant_aliases",
    "notified_transactions",
    "pushover_pending",
    "receipts",
    "recurring_cadence_overrides",
    "recurring_ignore_categories",
    "recurring_ignore_merchants",
    "recurring_ignore_patterns",
    "sinking_fund",
    "sinking_fund_ledger",
    "transaction_receipts",
    "ui_layout",
]
CURRENT_TENANT_ID: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)


def _table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS t", (f"public.{table}",))
    row = cur.fetchone() or {}
    return bool(row.get("t"))


def ensure_tenancy_tables():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id BIGSERIAL PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                google_sub TEXT UNIQUE,
                email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                tenant_id BIGINT REFERENCES tenants(id),
                is_owner BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                approved_at TIMESTAMPTZ
            )
            """
        )
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower_unique ON users ((lower(email)))")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users (tenant_id)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tenant_onboarding (
                tenant_id BIGINT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
                wizard_completed BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

        for table in CORE_TENANT_TABLES:
            if not _table_exists(cur, table):
                continue
            cur.execute(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS tenant_id BIGINT REFERENCES tenants(id)')
            cur.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_tenant_id ON "{table}" (tenant_id)')

        conn.commit()


def _ensure_owner_tenant(owner_email: str) -> int | None:
    if not owner_email:
        return None

    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO tenants (slug, name, status)
            VALUES ('owner', 'Owner Workspace', 'active')
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """
        )
        row = cur.fetchone()
        owner_tenant_id = int(row["id"])

        cur.execute(
            """
            INSERT INTO users (email, status, tenant_id, is_owner, approved_at)
            VALUES (%s, 'approved', %s, TRUE, now())
            ON CONFLICT ((lower(email))) DO UPDATE SET
                status = 'approved',
                tenant_id = EXCLUDED.tenant_id,
                is_owner = TRUE,
                approved_at = COALESCE(users.approved_at, now())
            """,
            (owner_email, owner_tenant_id),
        )
        conn.commit()

    return owner_tenant_id


def _backfill_owner_tenant(owner_tenant_id: int):
    with with_db_cursor() as (conn, cur):
        for table in CORE_TENANT_TABLES:
            if not _table_exists(cur, table):
                continue
            cur.execute(f'UPDATE "{table}" SET tenant_id = %s WHERE tenant_id IS NULL', (int(owner_tenant_id),))
        conn.commit()


def register_google_user(google_sub: str | None, email: str | None):
    if not MULTI_TENANT_ENABLED:
        return None
    e = (email or "").strip().lower()
    if not e:
        return None

    owner_email = (OWNER_GOOGLE_EMAIL or "").strip().lower()
    is_owner = bool(owner_email) and e == owner_email
    owner_tenant_id = _ensure_owner_tenant(owner_email) if is_owner else None

    with with_db_cursor() as (conn, cur):
        status_in = "approved" if is_owner else "pending"
        cur.execute(
            """
            INSERT INTO users (google_sub, email, status, tenant_id, is_owner, approved_at)
            VALUES (%s, %s, %s, %s, %s, CASE WHEN %s THEN now() ELSE NULL END)
            ON CONFLICT ((lower(email))) DO UPDATE SET
                google_sub = COALESCE(EXCLUDED.google_sub, users.google_sub),
                status = CASE WHEN EXCLUDED.is_owner THEN 'approved' ELSE users.status END,
                tenant_id = CASE WHEN EXCLUDED.is_owner THEN EXCLUDED.tenant_id ELSE users.tenant_id END,
                is_owner = users.is_owner OR EXCLUDED.is_owner,
                approved_at = CASE
                    WHEN EXCLUDED.is_owner THEN COALESCE(users.approved_at, now())
                    ELSE users.approved_at
                END
            RETURNING id, email, status, tenant_id, is_owner
            """,
            (
                google_sub,
                e,
                status_in,
                owner_tenant_id,
                is_owner,
                is_owner,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        out = dict(row) if row else None
        if out and out.get("status") == "pending":
            _notify_owner_pending_signup(e, int(out.get("id")))
        return out


def _notify_owner_pending_signup(email: str, user_id: int):
    owner_tenant_id = get_owner_tenant_id()
    if not owner_tenant_id:
        return
    dedupe_key = f"t{int(owner_tenant_id)}:pending-user:{email}"
    try:
        with with_db_cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO notifications (tenant_id, kind, dedupe_key, subject, sender, body, is_read, dismissed)
                VALUES (%s, %s, %s, %s, %s, %s, FALSE, FALSE)
                ON CONFLICT (dedupe_key) DO NOTHING
                """,
                (
                    int(owner_tenant_id),
                    "user_signup_pending",
                    dedupe_key,
                    "New user pending approval",
                    "Auth",
                    f"Email: {email}\nUser ID: {int(user_id)}",
                ),
            )
            conn.commit()
    except Exception:
        # Do not block user registration if notifications table/path is unavailable.
        return


def get_user_by_email(email: str | None):
    if not MULTI_TENANT_ENABLED:
        return None
    e = (email or "").strip().lower()
    if not e:
        return None
    with with_db_cursor() as (_, cur):
        cur.execute(
            """
            SELECT id, email, status, tenant_id, is_owner
            FROM users
            WHERE lower(email) = lower(%s)
            LIMIT 1
            """,
            (e,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def list_pending_users():
    if not MULTI_TENANT_ENABLED:
        return []
    with with_db_cursor() as (_, cur):
        cur.execute(
            """
            SELECT id, email, google_sub, status, tenant_id, is_owner, created_at
            FROM users
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            """
        )
        rows = cur.fetchall() or []
    return [dict(r) for r in rows]


def _slugify(s: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (s or "").strip().lower()).strip("-")
    return slug or "tenant"


def _next_unique_tenant_slug(cur, base_slug: str) -> str:
    cur.execute("SELECT slug FROM tenants WHERE slug = %s LIMIT 1", (base_slug,))
    if not cur.fetchone():
        return base_slug
    i = 2
    while True:
        candidate = f"{base_slug}-{i}"
        cur.execute("SELECT slug FROM tenants WHERE slug = %s LIMIT 1", (candidate,))
        if not cur.fetchone():
            return candidate
        i += 1


def approve_user(user_id: int, workspace_name: str | None = None):
    if not MULTI_TENANT_ENABLED:
        return None
    uid = int(user_id)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT id, email, status, tenant_id, is_owner
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (uid,),
        )
        user = cur.fetchone()
        if not user:
            return None

        if user.get("status") == "approved" and user.get("tenant_id"):
            return dict(user)

        email = (user.get("email") or "").strip().lower()
        name = (workspace_name or "").strip() or f"{email.split('@')[0] or 'User'} Workspace"
        slug = _slugify(email.split("@")[0])
        slug = _next_unique_tenant_slug(cur, slug)

        cur.execute(
            """
            INSERT INTO tenants (slug, name, status)
            VALUES (%s, %s, 'active')
            RETURNING id
            """,
            (slug, name),
        )
        tenant_id = int(cur.fetchone()["id"])

        cur.execute(
            """
            UPDATE users
            SET status = 'approved',
                tenant_id = %s,
                approved_at = COALESCE(approved_at, now())
            WHERE id = %s
            RETURNING id, email, status, tenant_id, is_owner
            """,
            (tenant_id, uid),
        )
        approved = cur.fetchone()

        owner_tenant_id = get_owner_tenant_id()
        if owner_tenant_id:
            dedupe_key = f"t{int(owner_tenant_id)}:pending-user:{email}"
            cur.execute(
                """
                UPDATE notifications
                SET dismissed = TRUE, is_read = TRUE
                WHERE dedupe_key = %s
                """,
                (dedupe_key,),
            )

        conn.commit()
        return dict(approved) if approved else None


def get_owner_tenant_id() -> int | None:
    if not MULTI_TENANT_ENABLED:
        return None
    with with_db_cursor() as (_, cur):
        cur.execute("SELECT id FROM tenants WHERE slug = 'owner' LIMIT 1")
        row = cur.fetchone()
    if not row:
        return None
    return int(row["id"])


def get_or_create_onboarding_state(tenant_id: int):
    tid = int(tenant_id)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO tenant_onboarding (tenant_id)
            VALUES (%s)
            ON CONFLICT (tenant_id) DO NOTHING
            """,
            (tid,),
        )
        cur.execute(
            """
            SELECT tenant_id, wizard_completed, created_at, updated_at
            FROM tenant_onboarding
            WHERE tenant_id = %s
            LIMIT 1
            """,
            (tid,),
        )
        row = cur.fetchone()
        conn.commit()
    return dict(row) if row else {"tenant_id": tid, "wizard_completed": False}


def set_onboarding_completed(tenant_id: int, completed: bool):
    tid = int(tenant_id)
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO tenant_onboarding (tenant_id, wizard_completed, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (tenant_id) DO UPDATE SET
                wizard_completed = EXCLUDED.wizard_completed,
                updated_at = now()
            """,
            (tid, bool(completed)),
        )
        conn.commit()


def set_current_tenant_id(tenant_id: int | None):
    return CURRENT_TENANT_ID.set(tenant_id)


def reset_current_tenant_id(token):
    CURRENT_TENANT_ID.reset(token)


def current_tenant_id() -> int | None:
    return CURRENT_TENANT_ID.get()


def initialize_tenancy():
    if not MULTI_TENANT_ENABLED:
        return

    ensure_tenancy_tables()
    owner_email = (OWNER_GOOGLE_EMAIL or "").strip().lower()
    owner_tenant_id = _ensure_owner_tenant(owner_email)
    if owner_tenant_id:
        _backfill_owner_tenant(owner_tenant_id)
        print(f"[tenancy] initialized owner tenant id={owner_tenant_id} email={owner_email}")
    else:
        print("[tenancy] MULTI_TENANT_ENABLED is true but OWNER_GOOGLE_EMAIL is not set")
