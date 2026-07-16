from __future__ import annotations

from collections import OrderedDict

from PySide6.QtGui import QPixmap

# Analogous to QuailAndroid's TileCache.kt (an in-memory LruCache<String,
# Bitmap> with a 48MB byte budget) — bounded by tile *count* here instead of
# measured byte size, which is a simplification but avoids walking each
# QPixmap's actual memory footprint on every insert. At TILE_SIZE_PX=256
# and roughly this cache size, memory use stays in the same ballpark as
# Android's budget without the extra bookkeeping.
_MAX_TILES = 512


class TileCache:
    """LRU cache of pre-rendered map tile QPixmaps, keyed by
    (zoom_index, tile_x, tile_y). Panning within the same zoom level reuses
    cached tiles instead of redrawing the whole road graph every frame;
    only newly-exposed tiles get rendered."""

    def __init__(self, max_tiles: int = _MAX_TILES):
        self._max_tiles = max_tiles
        self._store: OrderedDict[tuple[int, int, int], QPixmap] = OrderedDict()

    def get(self, key: tuple[int, int, int]) -> QPixmap | None:
        pixmap = self._store.get(key)
        if pixmap is not None:
            self._store.move_to_end(key)
        return pixmap

    def put(self, key: tuple[int, int, int], pixmap: QPixmap) -> None:
        self._store[key] = pixmap
        self._store.move_to_end(key)
        while len(self._store) > self._max_tiles:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
