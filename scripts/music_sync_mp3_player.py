#!/usr/bin/env python3
"""Syncs Jellyfin playlists onto the "SSD MP3" drive (or any USB drive)
plugged into this Mac.

Run manually whenever the player is plugged in:

    export JELLYFIN_API_KEY=<your Jellyfin API key>
    python3 scripts/music_sync_mp3_player.py "/Volumes/SSD MP3"

(Add the export line to ~/.zshrc so you don't have to retype it — the key
itself isn't stored in this file since it's checked into git. Generate one
in Jellyfin under Dashboard -> API Keys.)

The homelab's "Music manager" service (Explo) writes two kinds of
playlists into Jellyfin:

- Rotating ones named like "Daily-Jams-2026-Day192" and
  "Weekly-Exploration-2026-Week29" — a new dated entry appears on its own
  schedule, so only the newest of each is synced (by the trailing
  day/week number), not every historical one ever created.
- Everything else — custom playlists imported via Explo's "+ Import"
  (e.g. from scripts/listenbrainz_playlist_maker.py), or anything else
  you've made directly in Jellyfin. These aren't dated/rotating, so all
  of them are synced in full, every run.

Downloads tracks via the Jellyfin API and drops them into one folder per
playlist on the drive, replacing whatever was there for that playlist
from the last sync. Also writes an .m3u alongside each folder so Quail
Music (the car computer app) picks each one up as a real playlist, not
just a pile of files.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import requests

JELLYFIN_URL = "http://100.69.144.70:8096"
API_KEY = os.environ.get("JELLYFIN_API_KEY", "")

_ROTATING_PREFIXES = ("Daily-Jams-", "Weekly-Exploration-")
# Matches the trailing "2026-Day192" / "2026-Week29" style suffix — the
# meaningful ordering is the last integer in the name (day-of-year or
# week-of-year), not a lexical string compare.
_TRAILING_NUMBER = re.compile(r"(\d+)$")
_UNSAFE_FOLDER_CHARS = re.compile(r'[/\\:*?"<>|]')


def _get(path: str, **params) -> dict:
    params["api_key"] = API_KEY
    resp = requests.get(f"{JELLYFIN_URL}{path}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get_user_id() -> str:
    users = requests.get(f"{JELLYFIN_URL}/Users", params={"api_key": API_KEY}, timeout=30).json()
    if not users:
        raise RuntimeError("No Jellyfin users found for this API key")
    return users[0]["Id"]


def _sanitize_folder_name(name: str) -> str:
    return _UNSAFE_FOLDER_CHARS.sub("_", name).strip() or "Playlist"


def _playlists_to_sync(user_id: str) -> list[tuple[str, dict]]:
    """Returns [(display_name, playlist_dict), ...] — see the module
    docstring for the rotating-vs-custom distinction this implements."""
    items = _get(
        "/Items",
        userId=user_id,
        IncludeItemTypes="Playlist",
        Recursive="true",
    ).get("Items", [])

    rotating_latest: dict[str, dict] = {}
    custom: list[tuple[str, dict]] = []
    for item in items:
        name = item.get("Name", "")
        matched_prefix = next((p for p in _ROTATING_PREFIXES if name.startswith(p)), None)
        if matched_prefix is None:
            custom.append((_sanitize_folder_name(name), item))
            continue
        match = _TRAILING_NUMBER.search(name)
        if not match:
            continue
        number = int(match.group(1))
        existing = rotating_latest.get(matched_prefix)
        if not existing or number > existing["_number"]:
            rotating_latest[matched_prefix] = {**item, "_number": number}

    result = [
        (prefix.rstrip("-").replace("-", " "), playlist) for prefix, playlist in rotating_latest.items()
    ]
    result.extend(custom)
    return result


def _playlist_items(playlist_id: str, user_id: str) -> list[dict]:
    return _get(
        f"/Playlists/{playlist_id}/Items",
        userId=user_id,
        Fields="Path,MediaSources",
    ).get("Items", [])


def _real_extension(track: dict) -> str:
    # Container is an FFmpeg format-probe string (e.g. "mov,mp4,m4a,3gp,..."
    # for actual .m4a files) — not a usable file extension. The real
    # extension lives on the source file's Path instead.
    path = track.get("Path") or ""
    if not path:
        sources = track.get("MediaSources") or []
        if sources:
            path = sources[0].get("Path") or ""
    suffix = Path(path).suffix.lstrip(".")
    return suffix or "mp3"


def _track_filename(item_id: str, artist: str, title: str, extension: str) -> str:
    safe_title = re.sub(r'[/\\:*?"<>|]', "_", title) or item_id
    safe_artist = re.sub(r'[/\\:*?"<>|]', "_", artist) or "Unknown Artist"
    # Keyed by the Jellyfin item ID, not playlist position — a track's
    # filename now depends only on the track itself, never on where it
    # currently sits in the playlist. That's what makes the skip-if-
    # present check in sync_playlist() below actually work: reordering a
    # playlist (or a track appearing in two playlists) doesn't force a
    # redundant re-download just because its index changed.
    short_id = item_id[:8]
    return f"{safe_artist} - {safe_title} [{short_id}].{extension}"


def _download_track(item_id: str, dest_path: Path) -> None:
    resp = requests.get(
        f"{JELLYFIN_URL}/Items/{item_id}/Download",
        params={"api_key": API_KEY},
        stream=True,
        timeout=60,
    )
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            f.write(chunk)


def sync_playlist(display_name: str, playlist: dict, user_id: str, mount_path: Path) -> int:
    tracks = _playlist_items(playlist["Id"], user_id)
    print(f"{display_name} ({playlist['Name']}): {len(tracks)} track(s)")

    # Audio files live under one folder per artist at the drive's top
    # level (created on demand) — not one folder per playlist. A playlist
    # is now purely an .m3u pointing into those artist folders, so: (1)
    # "did the Paramore songs actually download" is answerable by just
    # looking for a Paramore folder, instead of having to dig through
    # whichever differently-named playlist folder happened to contain it,
    # and (2) a track shared by two playlists (or re-added to a rebuilt
    # Daily Jams) is only ever downloaded once — the second playlist's
    # sync finds it already sitting in its artist folder and skips it.
    m3u_lines = ["#EXTM3U"]
    downloaded, skipped = 0, 0
    for i, track in enumerate(tracks, start=1):
        artist = track.get("AlbumArtist") or (track.get("Artists") or [""])[0] or "Unknown Artist"
        title = track.get("Name", f"Track {i}")
        extension = _real_extension(track)
        artist_dir = mount_path / _sanitize_folder_name(artist)
        artist_dir.mkdir(parents=True, exist_ok=True)
        filename = _track_filename(track["Id"], artist, title, extension)
        dest_path = artist_dir / filename

        if dest_path.exists():
            skipped += 1
            print(f"  [{i}/{len(tracks)}] {artist} - {title} (already on drive)")
        else:
            _download_track(track["Id"], dest_path)
            downloaded += 1
            print(f"  [{i}/{len(tracks)}] {artist} - {title}")

        m3u_lines.append(f"#EXTINF:-1,{artist} - {title}")
        m3u_lines.append(str(dest_path.relative_to(mount_path)))

    # No per-playlist stale-file cleanup here anymore — a file now
    # potentially belongs to several playlists at once (shared artist
    # folder), so "not wanted by this one playlist" no longer means
    # "safe to delete." A track dropped from every playlist that ever
    # referenced it just becomes an orphaned file instead of being
    # auto-removed; cleaning those up is a separate, rarer concern this
    # pass doesn't try to solve.
    (mount_path / f"{display_name}.m3u").write_text("\n".join(m3u_lines) + "\n", encoding="utf-8")
    print(f"  {downloaded} downloaded, {skipped} already on drive")
    return len(tracks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mount_path", help='Path where the MP3 player is mounted, e.g. "/Volumes/SSD MP3"')
    args = parser.parse_args()

    if not API_KEY:
        print("error: set JELLYFIN_API_KEY in your environment first", file=sys.stderr)
        sys.exit(1)

    mount_path = Path(args.mount_path)
    if not mount_path.is_dir():
        print(f"error: {mount_path} is not a mounted directory", file=sys.stderr)
        sys.exit(1)

    user_id = _get_user_id()
    to_sync = _playlists_to_sync(user_id)
    if not to_sync:
        print("No playlists found in Jellyfin yet.")
        return

    summary_parts = []
    for display_name, playlist in to_sync:
        count = sync_playlist(display_name, playlist, user_id, mount_path)
        summary_parts.append(f"{display_name}: {count} tracks")

    print(f"\nDone syncing to {mount_path}: " + " • ".join(summary_parts))


if __name__ == "__main__":
    main()
