"""Syncs the master map database(s) onto the removable car hard drive.

Run manually whenever the drive is plugged into the homelab:

    .venv/bin/python scripts/maps_sync_car_drive.py /media/trevinjc/CARDRIVE

Copies the current master SQLite databases via rsync (incremental — only
changed regions actually get re-copied), writes a manifest.json onto the
drive recording what version of each region it now has, and records the
sync in Postgres so maps_check_car_drive_freshness.py knows the drive is
current again.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db

db.open_pool()
try:
    from app.core.maps_config import maps_enabled, master_dir
    from app.core.maps_state import get_master_state, record_car_drive_sync
    from app.core.tenancy import get_owner_tenant_id

    def log(msg: str) -> None:
        print(f"[maps_sync_car_drive] {msg}")

    def main() -> None:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("mount_path", help="Path where the car drive is mounted")
        parser.add_argument("--label", default="", help="Human-readable label for the drive")
        args = parser.parse_args()

        if not maps_enabled():
            log("MAPS_DATA_DIR is not set — nothing to sync")
            return

        mount_path = Path(args.mount_path)
        if not mount_path.is_dir():
            log(f"error: {mount_path} is not a mounted directory")
            sys.exit(1)

        rsync = shutil.which("rsync")
        if not rsync:
            log("error: rsync not found — install it (apt install rsync)")
            sys.exit(1)

        dest = mount_path / "quail_maps" / "master"
        dest.mkdir(parents=True, exist_ok=True)
        src = master_dir()

        log(f"rsyncing {src} -> {dest}")
        subprocess.run(
            [rsync, "-a", "--delete", f"{src}/", f"{dest}/"],
            check=True,
        )

        tenant_id = get_owner_tenant_id() or 0
        regions = get_master_state(tenant_id)
        manifest = {
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "regions": regions,
        }
        (mount_path / "quail_maps" / "manifest.json").write_text(json.dumps(manifest, indent=2))

        record_car_drive_sync(tenant_id, args.label or mount_path.name, regions)
        log(f"synced {len(regions)} region(s) to {mount_path}")

    main()
finally:
    db.close_pool()
