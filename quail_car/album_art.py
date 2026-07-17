from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

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


# Large enough to hold thumbnails for the whole library at once (rows build
# their widgets eagerly, not virtualized) without re-decoding on every
# rescan — most tracks on an album share one embedded cover, so the number
# of *distinct* images is normally well under the track count, but this is
# sized generously against total tracks anyway. Bounded — see
# _MAX_CACHED_DIMENSION for the other half of that memory tradeoff.
@lru_cache(maxsize=4000)
def _cached_image(path_str: str, mtime: float, size: int) -> QImage | None:
    # QImage, not QPixmap: this is called from the background scan thread
    # (see MusicScreen._LibraryScanThread) to pre-warm the cache before the
    # UI ever builds a row, so the actual disk read + JPEG/PNG decode never
    # blocks the main thread. QPixmap wraps a platform-native handle and
    # isn't safe to construct off the GUI thread; QImage is plain pixel
    # data and explicitly documented as thread-safe to build anywhere.
    data = _extract_cover_bytes(Path(path_str))
    if not data:
        return None
    image = QImage()
    if not image.loadFromData(data):
        return None
    if image.width() > _MAX_CACHED_DIMENSION or image.height() > _MAX_CACHED_DIMENSION:
        image = image.scaled(
            _MAX_CACHED_DIMENSION,
            _MAX_CACHED_DIMENSION,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return image


def warm_cache(path: Path) -> None:
    """Decodes + caches a track's cover art without touching QPixmap — safe
    to call from a background thread. Call this for the whole library right
    after a scan, so get_cover_pixmap() below is a cheap cache hit (just a
    fast QPixmap::fromImage conversion) by the time the UI actually needs
    it, instead of paying for file I/O + image decode on the UI thread."""
    get_cover_image(path)


def get_cover_image(path: Path) -> QImage | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return _cached_image(str(path), stat.st_mtime, stat.st_size)


def get_cover_pixmap(path: Path) -> QPixmap | None:
    image = get_cover_image(path)
    if image is None:
        return None
    return QPixmap.fromImage(image)
