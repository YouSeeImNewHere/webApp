#!/usr/bin/env python3
"""Syncs the latest Daily Jams / Weekly Exploration playlists from Jellyfin
onto the "SSD MP3" drive (or any USB drive) plugged into this Mac.

Run manually whenever the player is plugged in:

    export JELLYFIN_API_KEY=<your Jellyfin API key>
    python3 scripts/music_sync_mp3_player.py "/Volumes/SSD MP3"

(Add the export line to ~/.zshrc so you don't have to retype it — the key
itself isn't stored in this file since it's checked into git. Generate one
in Jellyfin under Dashboard -> API Keys.)

The homelab's "Music manager" service already writes playlists straight into
Jellyfin named like "Daily-Jams-2026-Day192" and
"Weekly-Exploration-2026-Week29" (confirmed in the Playlists library at
http://100.69.144.70:8096). This script finds the newest of each (by the
trailing day/week number), downloads their tracks via the Jellyfin API, and
drops them into folders on the drive — replacing whatever was there from the
last sync. It also writes an .m3u alongside each folder so Quail Music (the
car computer app) picks each one up as a real playlist, not just a pile of
files.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests

JELLYFIN_URL = "http://100.69.144.70:8096"
API_KEY = os.environ.get("JELLYFIN_API_KEY", "")

_PLAYLIST_PREFIXES = ("Daily-Jams-", "Weekly-Exploration-")
# Matches the trailing "2026-Day192" / "2026-Week29" style suffix — the
# meaningful ordering is the last integer in the name (day-of-year or
# week-of-year), not a lexical string compare.
_TRAILING_NUMBER = re.compile(r"(\d+)$")


def _applescript_string(value: str) -> str:
    # AppleScript string literals use double quotes; escape backslashes and
    # embedded quotes so track/artist names can't break out of the literal.
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _notify(title: str, message: str) -> None:
    # display dialog (a real modal popup) instead of display notification —
    # notification banners silently no-op if the calling app (Terminal/iTerm)
    # hasn't been granted Notification Center permission, which is easy to
    # miss. "giving up after 10" auto-dismisses so an unattended run doesn't
    # hang waiting for a click.
    script = (
        f"display dialog {_applescript_string(message)} "
        f"with title {_applescript_string(title)} "
        f"buttons {{\"OK\"}} default button \"OK\" giving up after 10"
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=15)
    except FileNotFoundError:
        pass  # not on macOS, or osascript missing — notification is best-effort


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


def _latest_playlists(user_id: str) -> dict[str, dict]:
    """Returns {prefix: playlist_dict} for the newest playlist under each prefix."""
    items = _get(
        "/Items",
        userId=user_id,
        IncludeItemTypes="Playlist",
        Recursive="true",
    ).get("Items", [])

    latest: dict[str, dict] = {}
    for item in items:
        name = item.get("Name", "")
        for prefix in _PLAYLIST_PREFIXES:
            if not name.startswith(prefix):
                continue
            match = _TRAILING_NUMBER.search(name)
            if not match:
                continue
            number = int(match.group(1))
            existing = latest.get(prefix)
            if not existing or number > existing["_number"]:
                latest[prefix] = {**item, "_number": number}
    return latest


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


def _download_track(item_id: str, dest_dir: Path, index: int, artist: str, title: str, extension: str) -> Path:
    safe_title = re.sub(r'[/\\:*?"<>|]', "_", title) or item_id
    safe_artist = re.sub(r'[/\\:*?"<>|]', "_", artist) or "Unknown Artist"
    filename = f"{index:02d} - {safe_artist} - {safe_title}.{extension}"
    dest_path = dest_dir / filename

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
    return dest_path


def sync_playlist(prefix: str, playlist: dict, user_id: str, mount_path: Path) -> int:
    display_name = prefix.rstrip("-").replace("-", " ")
    dest_dir = mount_path / display_name
    if dest_dir.exists():
        # ignore_errors: macOS Spotlight/Finder can touch "._" sidecar files
        # on external drives mid-rmtree, causing a FileNotFoundError race —
        # harmless since we're about to fully repopulate this folder anyway.
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    tracks = _playlist_items(playlist["Id"], user_id)
    print(f"{display_name} ({playlist['Name']}): {len(tracks)} track(s)")

    m3u_lines = ["#EXTM3U"]
    for i, track in enumerate(tracks, start=1):
        artist = track.get("AlbumArtist") or (track.get("Artists") or [""])[0]
        title = track.get("Name", f"Track {i}")
        extension = _real_extension(track)
        path = _download_track(track["Id"], dest_dir, i, artist, title, extension)
        m3u_lines.append(f"#EXTINF:-1,{artist} - {title}")
        m3u_lines.append(str(path.relative_to(mount_path)))
        print(f"  [{i}/{len(tracks)}] {artist} - {title}")

    (mount_path / f"{display_name}.m3u").write_text("\n".join(m3u_lines) + "\n", encoding="utf-8")
    return len(tracks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mount_path", help='Path where the MP3 player is mounted, e.g. "/Volumes/SSD MP3"')
    args = parser.parse_args()

    if not API_KEY:
        print("error: set JELLYFIN_API_KEY in your environment first", file=sys.stderr)
        _notify("Quail Music", "Sync failed: JELLYFIN_API_KEY not set")
        sys.exit(1)

    mount_path = Path(args.mount_path)
    if not mount_path.is_dir():
        print(f"error: {mount_path} is not a mounted directory", file=sys.stderr)
        _notify("Quail Music", f"Sync failed: {mount_path} isn't mounted")
        sys.exit(1)

    try:
        user_id = _get_user_id()
        latest = _latest_playlists(user_id)
        if not latest:
            print("No Daily-Jams-* or Weekly-Exploration-* playlists found in Jellyfin yet.")
            _notify("Quail Music", "No playlists found on Jellyfin to sync")
            return

        summary_parts = []
        for prefix, playlist in latest.items():
            display_name = prefix.rstrip("-").replace("-", " ")
            count = sync_playlist(prefix, playlist, user_id, mount_path)
            summary_parts.append(f"{display_name}: {count} tracks")
    except Exception as exc:
        _notify("Quail Music", f"Sync failed: {exc}")
        raise

    print(f"\nDone syncing to {mount_path}")
    _notify("Quail Music synced", " • ".join(summary_parts))


if __name__ == "__main__":
    main()
