from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import requests

from app.core.maps_config import geofabrik_state_url, geofabrik_url

# Log a download progress line at most this often, regardless of chunk size —
# keeps output readable on a fast connection without going silent on a slow one.
_PROGRESS_INTERVAL_SEC = 5.0


def _region_slug(region: str) -> str:
    return region.strip("/").replace("/", "_")


def fetch_region(
    region: str,
    raw_dir: Path,
    timeout: int = 1800,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> tuple[Path, bool]:
    """Downloads `region`'s latest .osm.pbf into `raw_dir` if Geofabrik's
    published md5 differs from what we already have on disk.

    Returns (pbf_path, changed). `changed` is False when the existing file's
    md5 already matches upstream, so callers can skip re-importing it.

    `on_progress(bytes_downloaded, total_bytes_or_None)` is called periodically
    during the download (total_bytes is None if Geofabrik doesn't send
    Content-Length) — this is the only signal a caller gets that anything is
    happening, since a multi-hundred-MB extract can take minutes.
    """
    slug = _region_slug(region)
    pbf_path = raw_dir / f"{slug}.osm.pbf"
    md5_path = raw_dir / f"{slug}.osm.pbf.md5"

    resp = requests.get(geofabrik_state_url(region), timeout=30)
    resp.raise_for_status()
    remote_md5 = resp.text.strip().split()[0].lower()

    local_md5 = md5_path.read_text().strip().split()[0].lower() if md5_path.exists() else None
    if local_md5 == remote_md5 and pbf_path.exists():
        return pbf_path, False

    with requests.get(geofabrik_url(region), stream=True, timeout=timeout) as r:
        r.raise_for_status()
        total = int(r.headers["Content-Length"]) if "Content-Length" in r.headers else None
        downloaded = 0
        last_report = time.monotonic()
        tmp_path = pbf_path.with_suffix(".pbf.part")
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if on_progress and now - last_report >= _PROGRESS_INTERVAL_SEC:
                    on_progress(downloaded, total)
                    last_report = now
        if on_progress:
            on_progress(downloaded, total)
        tmp_path.replace(pbf_path)

    md5_path.write_text(remote_md5)
    return pbf_path, True
