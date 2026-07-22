#!/usr/bin/env python3
"""Looks up a genre for every track on the MP3 player's drive via
MusicBrainz and writes them to quail_genres.json on the drive itself (see
quail_car/music_library.py's _load_genre_map) — the car computer has no
internet of its own, so this has to run here, on the Mac, whenever the
drive is plugged in, same as scripts/music_feedback_sync.py.

Run manually, or via scripts/music_sync_watch.sh whenever the drive mounts:

    python3 scripts/music_genre_sync.py "/Volumes/SSD MP3"

MusicBrainz recordings rarely have a curated "genre" field populated —
folksonomy tags (freeform, community-voted) are far more commonly present,
so this takes the recording's single highest-voted tag as a practical
stand-in for genre. That's a heuristic, not authoritative data: expect the
occasional odd/inconsistent result, not a clean taxonomy.

Results are cached in quail_genres.json itself — a re-run only looks up
artist/title pairs not already in that file, so this is safe (and cheap)
to run every time the drive comes home.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from mutagen import File as MutagenFile

from genre_normalize import normalize_genre

MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
USER_AGENT = "QuailMusic/1.0 ( personal car computer project )"

_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".aac"}
_EXCLUDED_DIR_NAMES = {"dcim", "movies", "audiobooks", "ebook", "lost.dir"}
GENRE_FILENAME = "quail_genres.json"
_GENRE_KEY_SEP = "|||"


def _genre_key(artist: str, title: str) -> str:
    return f"{artist}{_GENRE_KEY_SEP}{title}"


def _read_tags(path: Path) -> tuple[str, str]:
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None
    artist = title = ""
    if audio and audio.tags:
        artist = (audio.tags.get("artist") or [""])[0]
        title = (audio.tags.get("title") or [""])[0]
    return artist.strip() or "Unknown Artist", title.strip() or path.stem


def _scan_artist_titles(mount_path: Path) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for dirpath, dirnames, filenames in os.walk(mount_path):
        dirnames[:] = [d for d in dirnames if d.lower() not in _EXCLUDED_DIR_NAMES]
        for name in filenames:
            if name.startswith("._"):
                continue
            path = Path(dirpath) / name
            if path.suffix.lower() not in _AUDIO_EXTENSIONS:
                continue
            pairs.add(_read_tags(path))
    return pairs


def _best_tag(tags: list[dict]) -> str | None:
    if not tags:
        return None
    # Highest-voted tag, standing in for genre — see module docstring.
    return max(tags, key=lambda t: t.get("count", 0)).get("name")


def _lookup_recording(artist: str, title: str) -> dict | None:
    query = f'artist:"{artist}" AND recording:"{title}"'
    resp = requests.get(
        f"{MUSICBRAINZ_API}/recording",
        params={"query": query, "fmt": "json", "limit": 1, "inc": "tags+artist-credits"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    recordings = resp.json().get("recordings", [])
    return recordings[0] if recordings else None


def _lookup_artist_genre(artist_mbid: str, cache: dict[str, str | None]) -> str | None:
    # Individual recordings are tagged inconsistently on MusicBrainz — a
    # correctly-matched track very often has zero community tags even
    # though the *artist* entry does (artists get tagged far more
    # reliably than any one of their songs). Cached per artist rather
    # than per track since many tracks share the same artist — this is
    # the fallback path, not the common one, so it shouldn't multiply the
    # request count by the size of the whole library.
    if artist_mbid in cache:
        return cache[artist_mbid]
    time.sleep(1.0)
    resp = requests.get(
        f"{MUSICBRAINZ_API}/artist/{artist_mbid}",
        params={"fmt": "json", "inc": "tags"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    genre = _best_tag(resp.json().get("tags", []))
    cache[artist_mbid] = genre
    return genre


def sync(mount_path: Path) -> None:
    if artist_title_pairs := _scan_artist_titles(mount_path):
        print(f"Found {len(artist_title_pairs)} unique track(s) on the drive.")
    else:
        print("No audio files found on the drive.")
        return

    genre_path = mount_path / GENRE_FILENAME
    genres: dict[str, str] = {}
    if genre_path.exists():
        try:
            genres = json.loads(genre_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            genres = {}

    to_lookup = [
        (artist, title) for artist, title in artist_title_pairs
        if _genre_key(artist, title) not in genres
    ]
    if not to_lookup:
        print("Every track already has a cached genre — nothing to look up.")
        return

    print(f"Looking up {len(to_lookup)} track(s) not yet cached...")
    found_recording, found_artist, not_found, failed = 0, 0, 0, 0
    artist_genre_cache: dict[str, str | None] = {}

    for artist, title in to_lookup:
        try:
            # MusicBrainz asks unauthenticated clients to stay at ~1 req/sec.
            time.sleep(1.0)
            recording = _lookup_recording(artist, title)
            if recording is None:
                print(f"  no MusicBrainz match for {artist} - {title}")
                not_found += 1
                genres[_genre_key(artist, title)] = "Unknown Genre"
                continue

            genre = _best_tag(recording.get("tags", []))
            source = "recording"
            if genre is None:
                artist_credit = recording.get("artist-credit", [])
                artist_mbid = artist_credit[0]["artist"]["id"] if artist_credit else None
                if artist_mbid:
                    genre = _lookup_artist_genre(artist_mbid, artist_genre_cache)
                    source = "artist"

            if genre is None:
                print(f"  no genre found for {artist} - {title}")
                not_found += 1
                # Cached as empty so a re-run doesn't keep re-querying a
                # track MusicBrainz genuinely has no tags for anywhere
                # (neither the recording nor the artist).
                genres[_genre_key(artist, title)] = "Unknown Genre"
                continue

            bucket = normalize_genre(genre)
            genres[_genre_key(artist, title)] = bucket
            print(f"  {artist} - {title}: {genre} -> {bucket} (via {source})")
            if source == "recording":
                found_recording += 1
            else:
                found_artist += 1
        except requests.RequestException as exc:
            print(f"  failed {artist} - {title}: {exc}", file=sys.stderr)
            failed += 1

    genre_path.write_text(json.dumps(genres, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"\nDone: {found_recording} found via recording tags, {found_artist} via artist tags, "
        f"{not_found} had no genre anywhere, {failed} failed."
    )
    print(f"Wrote {genre_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mount_path", help='Path where the MP3 player is mounted, e.g. "/Volumes/SSD MP3"')
    args = parser.parse_args()

    mount_path = Path(args.mount_path)
    if not mount_path.is_dir():
        print(f"error: {mount_path} is not a mounted directory", file=sys.stderr)
        sys.exit(1)

    sync(mount_path)


if __name__ == "__main__":
    main()
