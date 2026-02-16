from __future__ import annotations

from app.core.config import MULTI_TENANT_ENABLED
from app.core.tenancy import current_tenant_id


def scoped_key(raw_key: str) -> str:
    key = (raw_key or "").strip()
    if not MULTI_TENANT_ENABLED:
        return key
    tid = current_tenant_id()
    if not tid:
        return key
    return f"t{int(tid)}:{key}"

