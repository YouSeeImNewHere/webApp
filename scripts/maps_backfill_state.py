"""One-off: backfills Postgres maps_master_state from master .sqlite3 files
already on disk, without re-downloading/re-importing anything.

Needed because an earlier version of maps_update_master.py recorded builds
under tenant_id=0 instead of the household's real owner tenant_id under
MULTI_TENANT_ENABLED — this reconciles existing on-disk data against the
correct tenant so /api/maps/status finds it. Safe to delete once run.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db

db.open_pool()
try:
    from app.core.maps_config import MAPS_REGION_SOURCES, master_dir, raw_dir
    from app.core.maps_state import record_region_build
    from app.core.tenancy import get_owner_tenant_id, initialize_tenancy

    def _region_slug(region: str) -> str:
        return region.strip("/").replace("/", "_")

    def main() -> None:
        initialize_tenancy()
        tenant_id = get_owner_tenant_id() or 0
        print(f"backfilling under tenant_id={tenant_id}")

        for region in MAPS_REGION_SOURCES:
            slug = _region_slug(region)
            master_db_path = master_dir() / f"{slug}.sqlite3"
            if not master_db_path.exists():
                print(f"  {region}: no master db at {master_db_path}, skipping")
                continue

            conn = sqlite3.connect(str(master_db_path))
            way_count = conn.execute("SELECT COUNT(*) FROM ways").fetchone()[0]
            node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            place_count = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
            conn.close()

            md5_path = raw_dir() / f"{slug}.osm.pbf.md5"
            source_md5 = md5_path.read_text().strip() if md5_path.exists() else ""

            stats = {
                "way_count": way_count,
                "node_count": node_count,
                "place_count": place_count,
                "size_bytes": master_db_path.stat().st_size,
            }
            record_region_build(tenant_id, region, stats, source_md5)
            print(f"  {region}: {stats}")

    main()
finally:
    db.close_pool()
