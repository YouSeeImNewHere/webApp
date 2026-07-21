#!/usr/bin/env python3
"""Standalone per-region importer for machines that can't reach homelab's
Postgres (e.g. the car computer, used here as a second, independent worker
to help clear the 51-state MAPS_REGION_SOURCES backlog faster). Skips
record_region_build()/tenancy entirely — deliberately, not an oversight —
since that DB write is just bookkeeping for /api/maps/status, not needed
to actually produce a usable master .sqlite3 file. Output files get copied
back onto homelab's /mnt/maps-data/master/ by hand once done.

Usage:
    .venv/bin/python scripts/standalone_region_import.py \
        [--pushover-key KEY] north-america/us/alaska north-america/us/arizona ...

Each region gets downloaded (if not already present) and imported into
./local_maps_data/master/<region-slug>.sqlite3, exactly matching the
naming maps_update_master.py already uses on homelab.

--pushover-key is a CLI flag, not read from the DB (unlike
maps_update_master.py's own per-region notification) — this machine has
no route to homelab's Postgres, so the key has to be handed in directly
rather than looked up.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.pushover import send_pushover
from maps_pipeline.geofabrik import fetch_region
from maps_pipeline.osm_import import import_region

DATA_DIR = Path(__file__).resolve().parents[1] / "local_maps_data"
RAW_DIR = DATA_DIR / "raw"
MASTER_DIR = DATA_DIR / "master"


def log(msg: str) -> None:
    print(f"[standalone_region_import] {msg}", flush=True)


def _region_slug(region: str) -> str:
    return region.strip("/").replace("/", "_")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pushover-key", default=None, help="Pushover user key to notify per region")
    parser.add_argument("regions", nargs="+")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MASTER_DIR.mkdir(parents=True, exist_ok=True)

    for region in args.regions:
        log(f"checking {region}")

        def _download_progress(downloaded: int, total: int | None):
            mb = downloaded / 1_048_576
            if total:
                pct = 100.0 * downloaded / total
                log(f"  downloading... {mb:,.0f} MB / {total / 1_048_576:,.0f} MB ({pct:.0f}%)")
            else:
                log(f"  downloading... {mb:,.0f} MB")

        pbf_path, _changed = fetch_region(region, RAW_DIR, on_progress=_download_progress)
        log(f"  download complete ({pbf_path.stat().st_size / 1_048_576:,.0f} MB), importing...")

        def _import_progress(way_count: int, place_count: int):
            log(f"  importing... {way_count:,} roads, {place_count:,} places so far")

        slug = _region_slug(region)
        master_db_path = MASTER_DIR / f"{slug}.sqlite3"
        stats = import_region(pbf_path, master_db_path, on_progress=_import_progress)
        log(f"  done: {region}: {stats}")
        if args.pushover_key:
            send_pushover(
                "Quail Maps (car computer)",
                f"{region} done — {stats['way_count']:,} roads, "
                f"{stats['place_count']:,} places ({stats['elapsed_sec']:.0f}s).",
                user_key=args.pushover_key,
            )

    log("all assigned regions processed")


if __name__ == "__main__":
    main()
