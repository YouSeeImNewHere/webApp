#!/usr/bin/env python3
"""One-off cleanup: re-buckets every genre already cached in
quail_genres.json using genre_normalize.normalize_genre(), without
re-running any MusicBrainz lookups. Run this once after adding/changing
the genre bucketing rules, so the ~1000+ tracks already looked up don't
need the whole multi-hour MusicBrainz pass repeated just to pick up a
classification change.

Run:
    python3 scripts/normalize_existing_genres.py "/Volumes/SSD MP3"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from genre_normalize import normalize_genre
from music_genre_sync import GENRE_FILENAME


def main() -> None:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <mount_path>", file=sys.stderr)
        sys.exit(1)

    mount_path = Path(sys.argv[1])
    if not mount_path.is_dir():
        print(f"error: {mount_path} is not a mounted directory", file=sys.stderr)
        sys.exit(1)

    genre_path = mount_path / GENRE_FILENAME
    if not genre_path.exists():
        print(f"No {GENRE_FILENAME} found at {mount_path} — nothing to normalize.")
        return

    genres: dict[str, str] = json.loads(genre_path.read_text(encoding="utf-8"))

    changed = 0
    before_buckets: dict[str, int] = {}
    after_buckets: dict[str, int] = {}
    for key, raw in genres.items():
        before_buckets[raw] = before_buckets.get(raw, 0) + 1
        bucket = normalize_genre(raw)
        after_buckets[bucket] = after_buckets.get(bucket, 0) + 1
        if bucket != raw:
            changed += 1
        genres[key] = bucket

    genre_path.write_text(json.dumps(genres, indent=2, sort_keys=True), encoding="utf-8")

    print(f"{len(genres)} track(s) total, {changed} re-bucketed.")
    print(f"\nBefore: {len(before_buckets)} distinct raw tag(s).")
    print(f"After: {len(after_buckets)} bucket(s):")
    for bucket, count in sorted(after_buckets.items(), key=lambda kv: -kv[1]):
        print(f"  {bucket}: {count}")


if __name__ == "__main__":
    main()
