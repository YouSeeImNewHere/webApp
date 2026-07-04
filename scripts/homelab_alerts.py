import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db

db.open_pool()
try:
    from app.core.homelab_metrics import get_homelab_metrics
    from app.core.tenancy import get_owner_tenant_id
    from app.routers.notifications import create_notification

    # Rough rules of thumb for a laptop repurposed as an always-on server —
    # not hard hardware limits, just "worth a look" thresholds.
    CPU_THRESHOLD = 85.0
    RAM_THRESHOLD = 85.0
    DISK_THRESHOLD = 85.0
    CORETEMP_THRESHOLD = 85.0
    NVME_THRESHOLD = 75.0
    DEFAULT_TEMP_THRESHOLD = 80.0

    def temp_threshold(label: str) -> float:
        low = label.lower()
        if "coretemp" in low:
            return CORETEMP_THRESHOLD
        if "nvme" in low:
            return NVME_THRESHOLD
        return DEFAULT_TEMP_THRESHOLD

    def main() -> None:
        metrics = get_homelab_metrics()
        if metrics.get("error"):
            return
        tenant_id = get_owner_tenant_id()
        if not tenant_id:
            return

        # Dedupe per-hour: a breach re-notifies once an hour while it persists,
        # rather than spamming every 5 minutes or going silent after the first hit.
        hour_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        alerts: list[tuple[str, str]] = []

        cpu = metrics.get("cpuUsedPercent")
        if cpu is not None and cpu > CPU_THRESHOLD:
            alerts.append(("cpu", f"CPU usage high: {cpu}%"))

        ram = metrics.get("ram") or {}
        ram_pct = ram.get("usedPercent")
        if ram_pct is not None and ram_pct > RAM_THRESHOLD:
            alerts.append(("ram", f"RAM usage high: {ram_pct}% ({ram.get('usedMB')}/{ram.get('totalMB')} MB)"))

        disk = metrics.get("diskRoot") or {}
        disk_pct = disk.get("usedPercent")
        if disk_pct is not None and disk_pct > DISK_THRESHOLD:
            alerts.append(("disk", f"Disk usage high: {disk_pct}% ({disk.get('usedGB')}/{disk.get('totalGB')} GB)"))

        for t in metrics.get("temperatures") or []:
            label = str(t.get("label") or "")
            celsius = t.get("celsius")
            if celsius is None or not label:
                continue
            if celsius > temp_threshold(label):
                alerts.append((f"temp_{label}", f"{label} temperature high: {celsius}°C"))

        for key, message in alerts:
            create_notification(
                kind="homelab_alert",
                dedupe_key=f"homelab_{key}_{hour_bucket}",
                subject="Homelab Server Alert",
                sender="Homelab",
                body=message,
                tenant_id=int(tenant_id),
            )

    main()
finally:
    db.close_pool()
