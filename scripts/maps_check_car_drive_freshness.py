"""Compares the removable car hard drive's last-synced map data against the
current master database and sends a "homelab_alert" notification (in-app +
Pushover/push, per existing notification prefs) if it's time to plug the
drive in and run maps_sync_car_drive.py.

Meant to run on a schedule (see deploy/systemd/quail-maps-freshness-check.timer),
staggered after quail-maps-update.timer so it's comparing against fresh data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db

db.open_pool()
try:
    from app.core.maps_config import MAPS_CAR_DRIVE_STALE_DAYS, maps_enabled
    from app.core.maps_state import car_drive_staleness
    from app.core.tenancy import get_owner_tenant_id, set_current_tenant_id, reset_current_tenant_id
    from app.core.time import today_local
    from app.routers.notifications import create_notification

    def main() -> None:
        if not maps_enabled():
            return
        tenant_id = get_owner_tenant_id()
        token = set_current_tenant_id(int(tenant_id)) if tenant_id else None
        try:
            state = car_drive_staleness(0, MAPS_CAR_DRIVE_STALE_DAYS)
            if not state["stale"]:
                return

            if state["reason"] == "never_synced":
                body = "Car map drive has never been synced. Plug it in and run maps_sync_car_drive.py."
            elif state["reason"] == "behind_regions":
                regions = ", ".join(state["behind_regions"])
                body = f"Car map drive is behind on: {regions}. Plug it in to update."
            else:
                days = state["days_since_sync"]
                body = f"Car map drive hasn't been synced in {days} days. Plug it in to update."

            # Include today's date so this re-notifies each time the weekly
            # timer finds it's still stale, instead of deduping forever
            # after the first alert.
            create_notification(
                kind="homelab_alert",
                dedupe_key=f"maps_car_drive_stale:{today_local().isoformat()}:{state['reason']}",
                subject="Quail Maps: car drive needs an update",
                sender="Quail Maps",
                body=body,
                tenant_id=int(tenant_id) if tenant_id else None,
            )
        finally:
            if token is not None:
                reset_current_tenant_id(token)

    main()
finally:
    db.close_pool()
