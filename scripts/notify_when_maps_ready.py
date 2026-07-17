#!/usr/bin/env python3
"""Waits for the nationwide maps import (by PID) and the Valhalla tile
build (by polling its HTTP service) to both finish, then sends a Pushover
notification to the account's stored key — same mechanism already used
for the daily budget / maps-freshness alerts, just triggered from here
instead of a scheduled job.

Run in the background on homelab:

    nohup .venv/bin/python scripts/notify_when_maps_ready.py <import_pid> \
        > /tmp/quail_maps_notify.log 2>&1 &
    disown
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import requests

# Python only puts the invoked script's own directory (scripts/) on
# sys.path, not the repo root — confirmed via a real ModuleNotFoundError
# for `db` (a top-level module at ~/webapp/db.py) when run directly as
# `python scripts/notify_when_maps_ready.py`. `app.*` imports happened to
# still work since that's a real package discoverable another way, but
# db.py isn't.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
from app.core.pushover import send_pushover
from app.core.tenancy import get_user_pushover_key_by_email

# Only one Quail account exists today — hardcoded rather than threading a
# --email flag through a one-off script that only ever gets run manually.
NOTIFY_EMAIL = "jaredtrevino03@gmail.com"

VALHALLA_STATUS_URL = "http://localhost:8002/status"
POLL_SECONDS = 60


def _pid_alive(pid: int) -> bool:
    try:
        subprocess.run(["kill", "-0", str(pid)], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _wait_for_import(pid: int) -> None:
    print(f"Waiting for maps import (PID {pid}) to finish...", flush=True)
    while _pid_alive(pid):
        time.sleep(POLL_SECONDS)
    print("Maps import finished.", flush=True)


def _wait_for_valhalla() -> None:
    # The scripted Valhalla image only starts serving on :8002 once tile
    # building has actually finished (build-then-serve, sequential) — a
    # real 200 from /status is a solid "tiles are ready" signal, not just
    # "the container is running."
    print("Waiting for Valhalla routing service to come up...", flush=True)
    while True:
        try:
            resp = requests.get(VALHALLA_STATUS_URL, timeout=5)
            if resp.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(POLL_SECONDS)
    print("Valhalla tiles ready.", flush=True)


def main() -> None:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <import_pid>", file=sys.stderr)
        sys.exit(1)
    import_pid = int(sys.argv[1])

    _wait_for_import(import_pid)
    _wait_for_valhalla()

    # get_user_pushover_key_by_email() goes through db.py's connection
    # pool, which db.py's own comment notes "assumes pool.open() was
    # called at startup" — true inside the running FastAPI app (its
    # lifespan handler does that), but not for a bare script importing
    # these modules directly. Real bug hit running this the first time:
    # psycopg_pool.PoolClosed: the pool 'pool-1' is not open yet.
    db.open_pool()
    key = get_user_pushover_key_by_email(NOTIFY_EMAIL)
    if not key:
        print("No Pushover key on file for this account — skipping notification.", file=sys.stderr)
        return
    sent = send_pushover(
        "Quail Maps",
        "Nationwide import and Valhalla tile build are both done.",
        user_key=key,
    )
    print(f"Notification sent: {sent}", flush=True)


if __name__ == "__main__":
    main()
