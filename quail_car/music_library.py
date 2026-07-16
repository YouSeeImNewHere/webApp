from __future__ import annotations

import getpass
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from mutagen import File as MutagenFile

_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".aac"}

# Non-music folders (photos, movies, audiobooks) can hold thousands of
# entries — walking into them made every scan take forever for zero benefit.
_EXCLUDED_DIR_NAMES = {"dcim", "movies", "audiobooks", "ebook", "lost.dir"}

# (mtime, size) -> (artist, title, album), so unchanged files skip the
# mutagen tag read on every rescan instead of re-parsing from scratch.
_tag_cache: dict[str, tuple[float, int, str, str, str]] = {}

# Playlists are stored on-device (not on the removable drive) so they
# survive swapping which USB stick is plugged in — same list, whatever
# media happens to be connected today.
PLAYLISTS_DIR = Path.home() / ".local" / "share" / "quail_music" / "playlists"

# Written by scripts/music_genre_sync.py (run on the Mac, where there's
# actual internet — this car computer has none of its own, same reason
# feedback_log.py writes to the drive instead of submitting anything
# directly) as {"artist|||title": "genre"}. Read here, never written.
GENRE_FILENAME = "quail_genres.json"
_GENRE_KEY_SEP = "|||"


def genre_key(artist: str, title: str) -> str:
    return f"{artist}{_GENRE_KEY_SEP}{title}"


def _load_genre_map(volume: Path) -> dict[str, str]:
    path = volume / GENRE_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@dataclass(frozen=True)
class Track:
    path: Path
    artist: str
    title: str
    album: str
    # Populated from GENRE_FILENAME on the drive (see _load_genre_map) if
    # scripts/music_genre_sync.py has been run for this artist/title —
    # never looked up live here, since the car has no internet of its own.
    genre: str = "Unknown Genre"

    @property
    def display(self) -> str:
        return f"{self.artist} — {self.title}" if self.artist != "Unknown Artist" else self.title


@dataclass
class Playlist:
    name: str
    tracks: list[Track] = field(default_factory=list)


def _media_roots() -> list[Path]:
    # Where udisks2 auto-mounts removable drives differs by Ubuntu version —
    # this mini PC uses /run/media/$USER, older ones use /media/$USER.
    user = getpass.getuser()
    return [Path(f"/run/media/{user}"), Path(f"/media/{user}")]


def _read_tags(path: Path) -> tuple[str, str, str]:
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None
    artist = title = album = ""
    if audio and audio.tags:
        artist = (audio.tags.get("artist") or [""])[0]
        title = (audio.tags.get("title") or [""])[0]
        album = (audio.tags.get("album") or [""])[0]
    return (
        artist.strip() or "Unknown Artist",
        title.strip() or path.stem,
        album.strip() or "Unknown Album",
    )


def scan_directory(root: Path, genre_map: dict[str, str] | None = None) -> list[Track]:
    tracks: list[Track] = []
    if not root.exists():
        return tracks
    genre_map = genre_map or {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in _EXCLUDED_DIR_NAMES]
        for name in filenames:
            # Skip macOS AppleDouble sidecar files (e.g. "._Song.mp3") that
            # Finder writes alongside real files on FAT32/exFAT.
            if name.startswith("._"):
                continue
            path = Path(dirpath) / name
            if path.suffix.lower() not in _AUDIO_EXTENSIONS:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            cache_key = str(path)
            signature = (stat.st_mtime, stat.st_size)
            cached = _tag_cache.get(cache_key)
            if cached and (cached[0], cached[1]) == signature:
                artist, title, album = cached[2], cached[3], cached[4]
            else:
                artist, title, album = _read_tags(path)
                _tag_cache[cache_key] = (signature[0], signature[1], artist, title, album)
            genre = genre_map.get(genre_key(artist, title), "Unknown Genre")
            tracks.append(Track(path=path, artist=artist, title=title, album=album, genre=genre))
    tracks.sort(key=lambda t: (t.artist.lower(), t.album.lower(), t.title.lower()))
    return tracks


def scan_library() -> list[Track]:
    tracks: list[Track] = []
    for root in _media_roots():
        if not root.exists():
            continue
        for volume in root.iterdir():
            if volume.is_dir():
                tracks.extend(scan_directory(volume, _load_genre_map(volume)))
    tracks.sort(key=lambda t: (t.artist.lower(), t.album.lower(), t.title.lower()))
    return tracks


def active_volume() -> Path | None:
    """First mounted removable volume, if any. The car computer has no
    internet of its own, so anything that needs to eventually leave the
    car (feedback events, same as playlists already do) gets written here
    instead — it physically travels out on the next trip home."""
    for root in _media_roots():
        if not root.exists():
            continue
        for volume in root.iterdir():
            if volume.is_dir():
                return volume
    return None


# The Playlists browse view calls load_playlist() once per playlist just to
# get a track count + cover, and each of those used to re-list the drive's
# top level from scratch — this short TTL means a burst of calls (one
# browse-view refresh, or a few keystrokes in search) shares one real
# directory listing instead of hitting the USB drive over and over.
_DRIVE_PLAYLIST_FILES_TTL = 4.0
_drive_playlist_files_cache: tuple[float, list[Path]] | None = None


def _drive_playlist_files() -> list[Path]:
    global _drive_playlist_files_cache
    now = time.monotonic()
    if _drive_playlist_files_cache is not None and now - _drive_playlist_files_cache[0] < _DRIVE_PLAYLIST_FILES_TTL:
        return _drive_playlist_files_cache[1]

    # Playlists synced onto the drive itself (e.g. by
    # scripts/music_sync_mp3_player.py, run at home before a trip) live at
    # the top level of the mounted volume, not under PLAYLISTS_DIR.
    files: list[Path] = []
    for root in _media_roots():
        if not root.exists():
            continue
        for volume in root.iterdir():
            if volume.is_dir():
                # Skip macOS AppleDouble sidecars (e.g. "._Daily Jams.m3u")
                # that Finder writes alongside real files on FAT32/exFAT —
                # same issue as the "._Song.mp3" ones filtered in scan_directory.
                files.extend(p for p in volume.glob("*.m3u") if not p.name.startswith("._"))

    _drive_playlist_files_cache = (now, files)
    return files


def list_playlist_names() -> list[str]:
    names = set()
    if PLAYLISTS_DIR.exists():
        names.update(p.stem for p in PLAYLISTS_DIR.glob("*.m3u"))
    names.update(p.stem for p in _drive_playlist_files())
    return sorted(names)


def _find_playlist_file(name: str) -> Path | None:
    local_path = PLAYLISTS_DIR / f"{name}.m3u"
    if local_path.exists():
        return local_path
    for path in _drive_playlist_files():
        if path.stem == name:
            return path
    return None


def _normalize(path: Path) -> str:
    # Pure string manipulation — no filesystem access. Path.resolve() was
    # used here before, but it hits the actual drive (stat/readlink) for
    # every path component; on a slow USB stick, doing that for every track
    # in every playlist on every list refresh is exactly what was freezing
    # the app. Removable FAT32/exFAT media has no symlinks to resolve
    # anyway, so normpath is just as correct and does zero I/O.
    return os.path.normpath(str(path))


def build_path_index(library: list[Track]) -> dict[str, Track]:
    """Precompute once per library snapshot and reuse across multiple
    load_playlist() calls (e.g. rendering every playlist row in the browse
    view) instead of rebuilding this dict from scratch each time."""
    return {_normalize(t.path): t for t in library}


def load_playlist(name: str, library: list[Track], path_index: dict[str, Track] | None = None) -> Playlist:
    by_path = path_index if path_index is not None else build_path_index(library)
    path = _find_playlist_file(name)
    tracks: list[Track] = []
    if path is not None:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entry = Path(line)
            resolved = entry if entry.is_absolute() else (path.parent / entry)
            track = by_path.get(_normalize(resolved))
            if track is not None:
                tracks.append(track)
    return Playlist(name=name, tracks=tracks)


def save_playlist(playlist: Playlist) -> None:
    PLAYLISTS_DIR.mkdir(parents=True, exist_ok=True)
    path = PLAYLISTS_DIR / f"{playlist.name}.m3u"
    lines = ["#EXTM3U"]
    for track in playlist.tracks:
        lines.append(f"#EXTINF:-1,{track.artist} - {track.title}")
        lines.append(str(track.path))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def delete_playlist(name: str) -> None:
    path = PLAYLISTS_DIR / f"{name}.m3u"
    if path.exists():
        path.unlink()
