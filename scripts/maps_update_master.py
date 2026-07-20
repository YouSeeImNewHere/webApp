"""Pulls each configured Geofabrik region (MAPS_REGION_SOURCES) and rebuilds
that region's master SQLite database if the upstream extract has changed.

Homelab only — requires `osmium` and real disk space (MAPS_DATA_DIR), not
run as part of the hosted web app.

Pass --force to reimport every configured region from its already-downloaded
.osm.pbf even if Geofabrik's upstream data hasn't changed — needed after
editing maps_pipeline/tags.py (e.g. adding new POI categories), since that's
a code change the md5-based "is there anything new to pull" check can't see.

Meant to run on a schedule (see deploy/systemd/quail-maps-update.timer).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.maps_config import MAPS_REGION_SOURCES, city_cache_dir, master_dir, maps_enabled, raw_dir, tile_cache_dir
from app.core.maps_state import record_region_build
from app.core.pushover import send_pushover
from app.core.tenancy import get_owner_tenant_id, get_user_pushover_key_by_email, initialize_tenancy
from db import open_pool, close_pool

# Only one Quail account exists today — hardcoded rather than threading a
# --email flag through a cron-scheduled script.
NOTIFY_EMAIL = "jaredtrevino03@gmail.com"


def log(msg: str) -> None:
    print(f"[maps_update_master] {msg}")


def _region_slug(region: str) -> str:
    return region.strip("/").replace("/", "_")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="reimport every region from its existing .osm.pbf even if unchanged upstream",
    )
    args = parser.parse_args()

    if not maps_enabled():
        log("MAPS_DATA_DIR is not set — nothing to do")
        return
    if not MAPS_REGION_SOURCES:
        log("MAPS_REGION_SOURCES is empty — configure at least one Geofabrik region, e.g. "
            "north-america/us/california")
        return

    from maps_pipeline.geofabrik import fetch_region
    from maps_pipeline.osm_import import import_region

    open_pool()
    initialize_tenancy()
    try:
        # record_region_build() takes an explicit tenant_id (unlike the
        # contextvar current_tenant_id() other routers read) since this runs
        # standalone via cron, not through an authenticated request — resolve
        # the household's one owner tenant so /api/maps/status (which reads
        # under the logged-in session's real tenant_id under multi-tenant
        # mode) actually finds what got built here.
        tenant_id = get_owner_tenant_id() or 0
        # Looked up once, not per region — same DB round-trip either way,
        # no reason to repeat it 50+ times in one run.
        pushover_key = get_user_pushover_key_by_email(NOTIFY_EMAIL)
        any_changed = False
        for region in MAPS_REGION_SOURCES:
            log(f"checking {region}")

            def _download_progress(downloaded: int, total: int | None):
                mb = downloaded / 1_048_576
                if total:
                    pct = 100.0 * downloaded / total
                    log(f"  downloading... {mb:,.0f} MB / {total / 1_048_576:,.0f} MB ({pct:.0f}%)")
                else:
                    log(f"  downloading... {mb:,.0f} MB")

            pbf_path, changed = fetch_region(region, raw_dir(), on_progress=_download_progress)
            if not changed and not args.force:
                log(f"  up to date, skipping rebuild")
                continue
            if not changed:
                log(f"  up to date upstream, reimporting anyway (--force)")
            any_changed = True
            log(f"  download complete ({pbf_path.stat().st_size / 1_048_576:,.0f} MB), importing...")

            def _import_progress(way_count: int, place_count: int):
                log(f"  importing... {way_count:,} roads, {place_count:,} places so far")

            slug = _region_slug(region)
            master_db_path = master_dir() / f"{slug}.sqlite3"
            stats = import_region(pbf_path, master_db_path, on_progress=_import_progress)
            md5_path = raw_dir() / f"{slug}.osm.pbf.md5"
            source_md5 = md5_path.read_text().strip() if md5_path.exists() else ""
            record_region_build(tenant_id, region, stats, source_md5)
            log(f"  done: {region}: {stats}")
            if pushover_key:
                send_pushover(
                    "Quail Maps",
                    f"{region} done — {stats['way_count']:,} roads, "
                    f"{stats['place_count']:,} places ({stats['elapsed_sec']:.0f}s).",
                    user_key=pushover_key,
                )

        if any_changed:
            for cache_dir, label in ((city_cache_dir(), "city extract"), (tile_cache_dir(), "tile")):
                if cache_dir.exists():
                    log(f"master data changed — clearing stale {label} cache")
                    shutil.rmtree(cache_dir)
                    cache_dir.mkdir(parents=True, exist_ok=True)
        log("all regions processed")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
