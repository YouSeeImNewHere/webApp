from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from .music_library import Track

# Cap how big a decoded cover we'll ever keep cached — list rows only ever
# need small thumbnails, and Now Playing tops out well under this. Keeps a
# library's worth of cached art from turning into hundreds of MB of
# full-resolution embedded images.
_MAX_CACHED_DIMENSION = 400


def _extract_cover_bytes(path: Path) -> bytes | None:
    suffix = path.suffix.lower()
    try:
        if suffix == ".mp3":
            tags = ID3(path)
            frames = tags.getall("APIC")
            return frames[0].data if frames else None

        if suffix in (".m4a", ".aac"):
            tags = MP4(path)
            covers = tags.tags.get("covr") if tags.tags else None
            return bytes(covers[0]) if covers else None

        if suffix == ".flac":
            audio = FLAC(path)
            return audio.pictures[0].data if audio.pictures else None

        # .ogg / .wav and anything else — best-effort generic fallback via
        # mutagen's picture-agnostic API (works for some Vorbis/Opus files).
        audio = MutagenFile(path)
        pictures = getattr(audio, "pictures", None)
        if pictures:
            return pictures[0].data
    except Exception:
        return None
    return None


# Large enough to hold thumbnails for a full browse list at once (rows build
# their widgets eagerly, not virtualized) without re-decoding on every
# rescan, but still bounded — see _MAX_CACHED_DIMENSION for the other half
# of that memory tradeoff.
@lru_cache(maxsize=128)
def _cached_pixmap(path_str: str, mtime: float, size: int) -> QPixmap | None:
    data = _extract_cover_bytes(Path(path_str))
    if not data:
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(data):
        return None
    if pixmap.width() > _MAX_CACHED_DIMENSION or pixmap.height() > _MAX_CACHED_DIMENSION:
        pixmap = pixmap.scaled(
            _MAX_CACHED_DIMENSION,
            _MAX_CACHED_DIMENSION,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return pixmap


def get_cover_pixmap(path: Path) -> QPixmap | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return _cached_pixmap(str(path), stat.st_mtime, stat.st_size)


def get_artist_pixmap(artist: str, library: list[Track]) -> QPixmap | None:
    # Local files don't carry a separate "artist photo" tag — the closest
    # honest stand-in is one of that artist's own embedded track covers.
    for track in library:
        if track.artist != artist:
            continue
        pixmap = get_cover_pixmap(track.path)
        if pixmap is not None:
            return pixmap
    return None
