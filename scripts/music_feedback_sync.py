#!/usr/bin/env python3
"""Reads like/dislike/skip events Quail Music logged onto the MP3 player
while it was in the car (see quail_car/feedback_log.py — the car computer
has no internet of its own, so the drive is the only way these events ever
leave it) and submits Like/Dislike to ListenBrainz's official feedback API.

Run manually, or automatically via scripts/music_sync_watch.sh whenever the
drive mounts:

    export LISTENBRAINZ_TOKEN=<your token from listenbrainz.org/settings/>
    python3 scripts/music_feedback_sync.py "/Volumes/SSD MP3"

Skips have no official ListenBrainz submission endpoint (LB's public API
doesn't model "started listening but didn't finish" as a first-class
concept) — they're appended to a local log on this Mac instead of being
silently dropped, in case you want to look at them later.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

LISTENBRAINZ_API = "https://api.listenbrainz.org/1"
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
USER_AGENT = "QuailMusic/1.0 ( personal car computer project )"

TOKEN = os.environ.get("LISTENBRAINZ_TOKEN", "")
FEEDBACK_FILENAME = "quail_feedback.jsonl"
SKIP_LOG_PATH = Path.home() / ".config" / "quail_music" / "skip_log.jsonl"

_SCORE_BY_ACTION = {"like": 1, "dislike": -1, "unlike": 0}


def _lookup_recording_mbid(artist: str, title: str) -> str | None:
    query = f'artist:"{artist}" AND recording:"{title}"'
    resp = requests.get(
        f"{MUSICBRAINZ_API}/recording",
        params={"query": query, "fmt": "json", "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    recordings = resp.json().get("recordings", [])
    return recordings[0]["id"] if recordings else None


def _submit_feedback(recording_mbid: str, score: int) -> None:
    resp = requests.post(
        f"{LISTENBRAINZ_API}/feedback/recording-feedback",
        json={"recording_mbid": recording_mbid, "score": score},
        headers={"Authorization": f"Token {TOKEN}"},
        timeout=15,
    )
    resp.raise_for_status()


def _log_skip_locally(event: dict) -> None:
    SKIP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SKIP_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def sync(mount_path: Path) -> None:
    feedback_path = mount_path / FEEDBACK_FILENAME
    if not feedback_path.exists():
        print("No feedback events found on the drive.")
        return

    events = []
    for line in feedback_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not events:
        print("Feedback file was empty.")
        return

    print(f"Found {len(events)} event(s) to process.")
    submitted, skipped_no_match, logged_skips, failed = 0, 0, 0, 0

    for event in events:
        action = event.get("action")
        artist = event.get("artist", "")
        title = event.get("title", "")

        if action == "skip":
            _log_skip_locally(event)
            logged_skips += 1
            continue

        score = _SCORE_BY_ACTION.get(action)
        if score is None:
            continue

        try:
            # MusicBrainz asks unauthenticated clients to stay at ~1 req/sec.
            time.sleep(1.0)
            mbid = _lookup_recording_mbid(artist, title)
            if mbid is None:
                print(f"  no MusicBrainz match for {artist} - {title}, skipping")
                skipped_no_match += 1
                continue
            _submit_feedback(mbid, score)
            print(f"  {action}: {artist} - {title}")
            submitted += 1
        except requests.RequestException as exc:
            print(f"  failed ({action}) {artist} - {title}: {exc}", file=sys.stderr)
            failed += 1

    print(
        f"\nDone: {submitted} submitted, {logged_skips} skips logged locally, "
        f"{skipped_no_match} had no MusicBrainz match, {failed} failed."
    )

    # Archive rather than delete — if a submission failed partway through,
    # you still have the raw events to retry instead of having lost them.
    archive_path = mount_path / f"quail_feedback.processed-{datetime.now():%Y%m%d%H%M%S}.jsonl"
    feedback_path.rename(archive_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mount_path", help='Path where the MP3 player is mounted, e.g. "/Volumes/SSD MP3"')
    args = parser.parse_args()

    if not TOKEN:
        print("error: set LISTENBRAINZ_TOKEN in your environment first", file=sys.stderr)
        sys.exit(1)

    mount_path = Path(args.mount_path)
    if not mount_path.is_dir():
        print(f"error: {mount_path} is not a mounted directory", file=sys.stderr)
        sys.exit(1)

    sync(mount_path)


if __name__ == "__main__":
    main()
