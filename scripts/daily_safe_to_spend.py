import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db

db.open_pool()
try:
    from app.core.tenancy import get_owner_tenant_id, set_current_tenant_id, reset_current_tenant_id
    from app.core.time import today_local
    from app.routers.category_rules import month_budget_home_cached

    def main() -> None:
        tenant_id = get_owner_tenant_id()
        if not tenant_id:
            return
        # month_budget_home_cached() reads the tenant from a contextvar (normally
        # set by the per-request auth middleware) — set it manually here since
        # this runs standalone via cron/systemd, not through an HTTP request.
        token = set_current_tenant_id(int(tenant_id))
        try:
            today = today_local()
            # force_refresh=True bypasses the cache so this actually recomputes
            # right now. allow_notifications=True is what actually emits
            # "Today's safe-to-spend" (plus other date-gated smart-budget
            # alerts) — every other caller of month_budget_home_cached leaves
            # this False, so an ordinary app-open recompute (which also runs
            # once the cached payload goes stale after midnight) can't steal
            # the notification before this scheduled run fires.
            month_budget_home_cached(today.year, today.month, force_refresh=True, allow_notifications=True)
        finally:
            reset_current_tenant_id(token)

    main()
finally:
    db.close_pool()
