from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QEventPoint,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from ..geo.roadnet import GRAPH
from ..geo.search_db import Place
from ..theme import ACCENT
from .tile_cache import TileCache

MIN_SCALE = 0.02
# This used to be 0.6, which was quietly clamping every close-zoom request
# (including nav mode's driving view) down to whatever 0.6 px/m actually
# shows — on an 800px-tall screen that's ±667m, nowhere near "just my road
# and its intersections." Raised (with real margin — the first attempt at
# 6.0 was itself still clamping a 45m driving-view request, caught by
# actually checking the resulting displayed radius instead of assuming a
# bigger number was automatically enough) so a genuine street-level view is
# actually reachable instead of silently capped.
MAX_SCALE = 150.0

# Discrete zoom "snap points" the tile cache renders at, geometrically
# spaced by the same 1.3x step zoom_in()/zoom_out() already used — mirrors
# QuailAndroid's integer z11-z18 slippy-map levels, just adapted to this
# app's local flat-meter coordinate frame instead of lat/lon Web Mercator.
# Panning within one zoom level reuses cached tiles; the displayed image is
# scaled slightly to match the continuous _scale between snap points, the
# same way real slippy maps look a bit soft until the next zoom snap.
ZOOM_LEVELS: list[float] = []
_level = MIN_SCALE
while _level < MAX_SCALE:
    ZOOM_LEVELS.append(_level)
    _level *= 1.3
ZOOM_LEVELS.append(MAX_SCALE)

TILE_SIZE_PX = 256

# How far down the screen the car sits in nav mode — 0.5 would be dead
# center; higher pushes it toward the bottom so more of the road ahead is
# visible than behind, the "camera behind the car" part of the effect.
_NAV_ANCHOR_Y_FRACTION = 0.72

# Street name labels only render into tiles at or above this zoom (pixels
# per meter) — matches the tight driving-zoom scale NavScreen actually
# uses, so labels only ever show up when there's real room to read them.
_LABEL_MIN_TILE_SCALE = 0.35
_LABEL_FONT = QFont()
_LABEL_FONT.setPixelSize(12)
_LABEL_FONT.setWeight(QFont.DemiBold)

# Spatial grid cell size (meters) for indexing GRAPH.edges. Without this,
# rendering a tile meant scanning *every* edge in the whole graph to find
# the handful that overlap it — fine against the 18-edge synthetic network,
# but against a real OSM extract (tens of thousands of edges from
# way_nodes) that's a whole-graph scan per tile, times every visible tile,
# times every zoom level ever visited — exactly what froze the app the
# first time a real extract loaded. Built once and reused for the whole
# GRAPH's lifetime (rebuilt only if the app restarts with different data).
_EDGE_GRID_CELL_M = 1000.0
_edge_grid_cache: dict[tuple[int, int], list] | None = None


# If a single edge's bounding box would span more than this many grid
# cells, it gets bucketed as "long" instead of inserted into every cell it
# crosses — real OSM ways are almost always short segments between
# adjacent nodes, but an occasional long one (a highway segment, a bridge,
# a coastline-following road) shouldn't be able to blow up index-build time
# by fanning out into thousands of cell insertions.
_MAX_CELLS_PER_EDGE = 64

_LONG_EDGES_KEY = "__long__"


def _edge_grid() -> dict:
    global _edge_grid_cache
    if _edge_grid_cache is not None:
        return _edge_grid_cache

    grid: dict = {_LONG_EDGES_KEY: []}
    cell = _EDGE_GRID_CELL_M
    for edge in GRAPH.edges:
        a = GRAPH.nodes.get(edge.a)
        b = GRAPH.nodes.get(edge.b)
        if a is None or b is None:
            continue
        min_e, max_e = min(a.east, b.east), max(a.east, b.east)
        min_n, max_n = min(a.north, b.north), max(a.north, b.north)
        cx_min, cx_max = math.floor(min_e / cell), math.floor(max_e / cell)
        cy_min, cy_max = math.floor(min_n / cell), math.floor(max_n / cell)

        cell_count = (cx_max - cx_min + 1) * (cy_max - cy_min + 1)
        if cell_count > _MAX_CELLS_PER_EDGE:
            grid[_LONG_EDGES_KEY].append(edge)
            continue

        for cx in range(cx_min, cx_max + 1):
            for cy in range(cy_min, cy_max + 1):
                grid.setdefault((cx, cy), []).append(edge)

    _edge_grid_cache = grid
    return grid


def _edges_near(min_e: float, max_e: float, min_n: float, max_n: float) -> set:
    cell = _EDGE_GRID_CELL_M
    grid = _edge_grid()
    cx_min, cx_max = math.floor(min_e / cell), math.floor(max_e / cell)
    cy_min, cy_max = math.floor(min_n / cell), math.floor(max_n / cell)
    found: set = set(grid[_LONG_EDGES_KEY])
    for cx in range(cx_min, cx_max + 1):
        for cy in range(cy_min, cy_max + 1):
            found.update(grid.get((cx, cy), ()))
    return found


class MapCanvas(QWidget):
    """Renders the local road graph via a tile cache: the road network is
    pre-rendered once per (zoom level, tile) into a QPixmap and reused on
    every subsequent pan/repaint that revisits it, instead of iterating the
    full graph and redrawing every edge on every frame. POIs, the active
    route, and the user's position are drawn as a live overlay on top of
    the cached tiles, since those change often and are cheap to redraw.
    Pan with drag, zoom with the scroll wheel or the +/- buttons."""

    # Emitted when nav-mode auto-follow turns on/off — a manual pan or zoom
    # while driving pauses it (see mousePressEvent/wheelEvent below), so the
    # camera doesn't get yanked back to the car mid-look-around; the host
    # screen listens for this to show/hide a "recenter" button.
    follow_mode_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        # Real touch handling below (event() override) instead of relying
        # on the platform to synthesize mouse events from touch input —
        # on this embedded Linux touchscreen, plain single-finger drag was
        # reportedly doing nothing at all, which points at exactly that
        # synthesis not happening reliably. This also makes real
        # multi-touch (pinch-to-zoom) possible at all, which mouse events
        # fundamentally can't represent.
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self._center = (0.0, 0.0)
        self._scale = 0.1  # pixels per meter
        self._places: list[Place] = []
        self._route_points: list[tuple[float, float]] = []
        self._user_pos = (0.0, 0.0)
        self._dragging = False
        self._drag_last: QPointF | None = None
        self._tile_cache = TileCache()
        # Nav mode: heading-up rotation + a behind-the-car viewpoint, the
        # way real turn-by-turn apps look while actually driving. Off by
        # default (idle/browsing screens stay north-up with a plain dot);
        # NavScreen turns it on for the duration of an active drive.
        self._nav_mode = False
        self._heading = 0.0
        # Only meaningful in nav mode — True means the camera tracks the
        # car automatically every position update; a manual pan/zoom flips
        # this off until recenter() is called (typically via a button tap).
        self._follow_mode = True
        # Active touch points by id, for pan (1 finger) and pinch (2).
        self._touch_points: dict[int, QPointF] = {}
        self._pinch_last_dist: float | None = None

    # ---- public API ----

    def set_places(self, places: list[Place]) -> None:
        self._places = places
        self.update()

    def set_route(self, points: list[tuple[float, float]]) -> None:
        self._route_points = points
        self.update()

    def clear_route(self) -> None:
        self._route_points = []
        self.update()

    def set_user_position(self, east: float, north: float) -> None:
        self._user_pos = (east, north)
        self.update()

    def set_heading(self, degrees: float) -> None:
        """0 = facing north, 90 = facing east, etc. — same bearing
        convention already used by geo/routing.py's _bearing()."""
        self._heading = degrees % 360.0
        self.update()

    def set_nav_mode(self, enabled: bool) -> None:
        self._nav_mode = enabled
        if enabled:
            self._follow_mode = True
        self.update()

    def follow(self, east: float, north: float, heading: float) -> None:
        """The per-tick camera update while actively driving — unlike
        set_user_position()/set_heading(), this only actually moves the
        camera if the user hasn't manually panned/zoomed away; the car's
        real position and the arrow marker's heading still update either
        way, so panning around never shows a stale arrow."""
        self._user_pos = (east, north)
        self._heading = heading % 360.0
        if self._follow_mode:
            self._center = (east, north)
        self.update()

    def recenter(self) -> None:
        """Resume auto-follow after a manual pan/zoom — typically wired to
        a "recenter" button that appears while follow is paused."""
        was_following = self._follow_mode
        self._follow_mode = True
        self._center = self._user_pos
        self.update()
        if not was_following:
            self.follow_mode_changed.emit(True)

    def center_on(self, east: float, north: float) -> None:
        self._center = (east, north)
        self.update()

    def center_on_with_radius(self, east: float, north: float, radius_m: float) -> None:
        """Show a fixed radius around a point — unlike frame_points(), this
        deliberately ignores how far-flung the loaded data is. The default
        view on open should be "my immediate area," not zoomed out to fit
        every place that happens to be loaded; the user zooms out manually
        if they want to see farther."""
        self._center = (east, north)
        # Floor only guards against a literal zero/negative radius, not a
        # deliberately tight one — this used to be 50.0, which was quietly
        # overriding nav mode's 45m driving-view request the same way the
        # old MAX_SCALE was, just from the other direction.
        half_span = max(radius_m, 5.0)
        scale = min(self.width(), self.height()) / 2 / half_span
        self._scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        self.update()

    def frame_points(
        self,
        points: list[tuple[float, float]],
        padding: float = 1.4,
        margins: tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> None:
        """Fit the given world points into the area of this widget not
        covered by overlaid UI chrome. margins = (top, right, bottom, left)
        in pixels, e.g. to keep points out from under a bottom control
        panel."""
        if not points:
            return
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        mid_x = (min_x + max_x) / 2
        mid_y = (min_y + max_y) / 2

        span_x = max(max_x - min_x, 50.0) * padding
        span_y = max(max_y - min_y, 50.0) * padding

        top, right, bottom, left = margins
        avail_w = max(self.width() - left - right, 100)
        avail_h = max(self.height() - top - bottom, 100)
        scale = min(avail_w / span_x, avail_h / span_y)
        scale = max(MIN_SCALE, min(MAX_SCALE, scale))

        avail_center_x = left + avail_w / 2
        avail_center_y = top + avail_h / 2
        # sx = W/2 + (east-cx)*scale, sy = H/2 - (north-cy)*scale — solving
        # each for cx/cy so the bbox center maps to (avail_center_x, avail_center_y).
        cx = mid_x - (avail_center_x - self.width() / 2) / scale
        cy = mid_y + (avail_center_y - self.height() / 2) / scale

        self._center = (cx, cy)
        self._scale = scale
        self.update()

    def zoom_in(self) -> None:
        self._break_follow()
        self._scale = min(MAX_SCALE, self._scale * 1.3)
        self.update()

    def zoom_out(self) -> None:
        self._break_follow()
        self._scale = max(MIN_SCALE, self._scale / 1.3)
        self.update()

    def _break_follow(self) -> None:
        # Only meaningful in nav mode — idle/browsing screens don't have a
        # "follow" concept to break. A manual pan or zoom while driving
        # pauses auto-follow until recenter() is called (typically via a
        # button that appears while paused), so looking around doesn't get
        # immediately yanked back to the car on the next position update.
        if self._nav_mode and self._follow_mode:
            self._follow_mode = False
            self.follow_mode_changed.emit(False)

    # ---- coordinate transform ----

    def _to_screen(self, east: float, north: float) -> QPointF:
        cx, cy = self._center
        sx = self.width() / 2 + (east - cx) * self._scale
        sy = self.height() / 2 - (north - cy) * self._scale
        return QPointF(sx, sy)

    def _to_world(self, screen: QPointF) -> tuple[float, float]:
        cx, cy = self._center
        east = cx + (screen.x() - self.width() / 2) / self._scale
        north = cy - (screen.y() - self.height() / 2) / self._scale
        return east, north

    # ---- interaction ----

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._break_follow()
            self._dragging = True
            self._drag_last = event.position()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging and self._drag_last is not None:
            delta = event.position() - self._drag_last
            self._drag_last = event.position()
            cx, cy = self._center
            self._center = (cx - delta.x() / self._scale, cy + delta.y() / self._scale)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False
        self._drag_last = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    # ---- touch (pan with 1 finger, pinch-to-zoom with 2) ----

    def event(self, event) -> bool:
        et = event.type()
        # TEMPORARY DIAGNOSTIC — remove once we know what's actually
        # arriving at this widget when the screen is touched.
        if et in (
            QEvent.Type.TouchBegin,
            QEvent.Type.TouchUpdate,
            QEvent.Type.TouchEnd,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonRelease,
        ):
            print(f"[touch-debug] event type={et}", flush=True)
        if et in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            print(f"[touch-debug]   points={len(event.points())}", flush=True)
            self._handle_touch(event)
            # Consumed here, deliberately — letting this fall through would
            # let Qt *also* synthesize a mouse event from the same physical
            # touch, double-handling the same finger movement.
            return True
        return super().event(event)

    def _handle_touch(self, event) -> None:
        # Persistent per-finger state, merged in incrementally by point id
        # and explicit Released state — NOT "replace with whatever this
        # event's points() contains." The first version assumed every
        # event carries the complete current set of active touch points;
        # on this touch driver that assumption was false — pinch never
        # triggered because each finger's movement apparently arrives as
        # its own separate single-point event, so len(current) was never
        # actually 2 at once even with two fingers down. Tracking state
        # ourselves works regardless of which way a given driver reports it.
        self._break_follow()
        previous = dict(self._touch_points)

        for p in event.points():
            if p.state() == QEventPoint.State.Released:
                self._touch_points.pop(p.id(), None)
            else:
                self._touch_points[p.id()] = p.position()

        active_ids = sorted(self._touch_points.keys())

        if len(active_ids) == 1:
            point_id = active_ids[0]
            if point_id in previous:
                delta = self._touch_points[point_id] - previous[point_id]
                cx, cy = self._center
                self._center = (cx - delta.x() / self._scale, cy + delta.y() / self._scale)
                self.update()
            self._pinch_last_dist = None
        elif len(active_ids) >= 2:
            id1, id2 = active_ids[0], active_ids[1]
            p1, p2 = self._touch_points[id1], self._touch_points[id2]
            dist = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            if id1 in previous and id2 in previous and self._pinch_last_dist and self._pinch_last_dist > 1.0:
                factor = dist / self._pinch_last_dist
                self._scale = max(MIN_SCALE, min(MAX_SCALE, self._scale * factor))
                self.update()
            self._pinch_last_dist = dist
        else:
            self._pinch_last_dist = None

    # ---- painting ----

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0a0d13"))

        painter.save()
        if self._nav_mode and self._follow_mode:
            # Heading-up rotation + a behind-the-car viewpoint only while
            # actually following — once the user pans/zooms away, this
            # drops back to a plain, unrotated free-look view instead of
            # fighting every drag against a spinning frame. recenter()
            # brings both the camera and this rotation back.
            #
            # Rotate the whole scene around the car's own screen position
            # so the direction of travel always points up, then move that
            # pivot down toward the lower part of the screen so there's
            # more road visible ahead than behind — the same "just above
            # and behind the car" framing real turn-by-turn apps use.
            # Every draw call below still uses the same _to_screen()-computed
            # logical coordinates as always; this transform is what maps
            # them into the rotated/offset device space.
            pivot = self._to_screen(*self._user_pos)
            anchor = QPointF(self.width() / 2, self.height() * _NAV_ANCHOR_Y_FRACTION)
            painter.translate(anchor)
            painter.rotate(-self._heading)
            painter.translate(-pivot)

        # Antialiasing + smooth pixmap scaling here would apply to every
        # single tile blit, on every repaint, including every mouse-move
        # event during a drag — on Qt's CPU software rasterizer (no GPU on
        # the mini PC, unlike the Pixel 7a's hardware-accelerated Compose
        # rendering), that's a real, well-known perf killer for repeated
        # scaled-pixmap compositing. Off here; only the much cheaper
        # overlay draws below (route line, a handful of dots, one user
        # marker) opt back in, since those actually benefit visually and
        # are cheap regardless of antialiasing.
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        self._draw_road_tiles(painter)

        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._route_points:
            self._draw_route(painter)
        self._draw_places(painter)
        self._draw_user(painter)
        painter.restore()

    # ---- tiled road rendering ----

    def _nearest_zoom_index(self) -> int:
        # Nearest in log-space, since the levels are geometrically spaced.
        target = math.log(self._scale)
        return min(
            range(len(ZOOM_LEVELS)),
            key=lambda i: abs(math.log(ZOOM_LEVELS[i]) - target),
        )

    def _draw_road_tiles(self, painter: QPainter) -> None:
        if not GRAPH.edges:
            return
        zoom_idx = self._nearest_zoom_index()
        tile_scale = ZOOM_LEVELS[zoom_idx]
        tile_size_m = TILE_SIZE_PX / tile_scale

        half_w_m = self.width() / 2 / self._scale
        half_h_m = self.height() / 2 / self._scale
        cx, cy = self._center

        tx_min = math.floor((cx - half_w_m) / tile_size_m)
        tx_max = math.floor((cx + half_w_m) / tile_size_m)
        ty_min = math.floor((cy - half_h_m) / tile_size_m)
        ty_max = math.floor((cy + half_h_m) / tile_size_m)

        for tx in range(tx_min, tx_max + 1):
            for ty in range(ty_min, ty_max + 1):
                pixmap = self._get_or_render_tile(zoom_idx, tx, ty, tile_scale, tile_size_m)
                world_left = tx * tile_size_m
                world_bottom = ty * tile_size_m
                world_right = world_left + tile_size_m
                world_top = world_bottom + tile_size_m
                # North is up, so the world's top edge is the screen's top —
                # _to_screen already flips the y axis for us.
                top_left = self._to_screen(world_left, world_top)
                bottom_right = self._to_screen(world_right, world_bottom)
                painter.drawPixmap(QRectF(top_left, bottom_right), pixmap, QRectF(pixmap.rect()))

    def _get_or_render_tile(
        self, zoom_idx: int, tx: int, ty: int, tile_scale: float, tile_size_m: float
    ) -> QPixmap:
        key = (zoom_idx, tx, ty)
        cached = self._tile_cache.get(key)
        if cached is not None:
            return cached
        pixmap = self._render_tile(tx, ty, tile_scale, tile_size_m)
        self._tile_cache.put(key, pixmap)
        return pixmap

    def _render_tile(self, tx: int, ty: int, tile_scale: float, tile_size_m: float) -> QPixmap:
        pixmap = QPixmap(TILE_SIZE_PX, TILE_SIZE_PX)
        pixmap.fill(Qt.transparent)
        tile_painter = QPainter(pixmap)
        tile_painter.setRenderHint(QPainter.Antialiasing)

        origin_e = tx * tile_size_m
        origin_n = ty * tile_size_m

        def to_tile_px(east: float, north: float) -> QPointF:
            px = (east - origin_e) * tile_scale
            py = TILE_SIZE_PX - (north - origin_n) * tile_scale
            return QPointF(px, py)

        # Cheap per-edge bounding-box cull against the tile's world bbox
        # (with a small margin for line width) — a QPixmap paint device
        # clips anything drawn outside its own bounds automatically, so a
        # bbox-level overlap check is enough; no need for real line-segment
        # clipping to get correct-looking tile edges.
        margin_m = 8.0 / tile_scale
        tile_min_e, tile_max_e = origin_e - margin_m, origin_e + tile_size_m + margin_m
        tile_min_n, tile_max_n = origin_n - margin_m, origin_n + tile_size_m + margin_m

        # One label per street name per tile (not one per segment) — a
        # street usually crosses a tile as several edges, and repeating its
        # name at every one of them would be clutter, not clarity.
        labeled_streets: set[str] = set()

        for edge in _edges_near(tile_min_e, tile_max_e, tile_min_n, tile_max_n):
            a = GRAPH.nodes[edge.a]
            b = GRAPH.nodes[edge.b]
            edge_min_e, edge_max_e = min(a.east, b.east), max(a.east, b.east)
            edge_min_n, edge_max_n = min(a.north, b.north), max(a.north, b.north)
            if edge_max_e < tile_min_e or edge_min_e > tile_max_e:
                continue
            if edge_max_n < tile_min_n or edge_min_n > tile_max_n:
                continue

            p1 = to_tile_px(a.east, a.north)
            p2 = to_tile_px(b.east, b.north)
            if edge.road_class == "highway":
                pen = QPen(QColor("#3a4356"), 6, Qt.SolidLine, Qt.RoundCap)
            else:
                pen = QPen(QColor("#242c3a"), 4, Qt.SolidLine, Qt.RoundCap)
            tile_painter.setPen(pen)
            tile_painter.drawLine(p1, p2)

            # Only at close zoom — labeling every road at a zoomed-out
            # overview scale would just be visual noise, and there isn't
            # room for readable text on a short on-screen segment anyway.
            # Baked into the cached tile bitmap itself (not drawn fresh
            # every frame), so this costs nothing beyond the one-time
            # per-tile render.
            if (
                tile_scale >= _LABEL_MIN_TILE_SCALE
                and edge.street
                and edge.street not in labeled_streets
                and p1 != p2
            ):
                labeled_streets.add(edge.street)
                mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                angle = math.degrees(math.atan2(p2.y() - p1.y(), p2.x() - p1.x()))
                if angle > 90 or angle < -90:
                    angle += 180  # keep text upright, never printed upside-down
                tile_painter.save()
                tile_painter.translate(mid)
                tile_painter.rotate(angle)
                tile_painter.setFont(_LABEL_FONT)
                tile_painter.setPen(QPen(QColor("#c7cedb")))
                tile_painter.drawText(QRectF(-70, -18, 140, 16), Qt.AlignCenter, edge.street)
                tile_painter.restore()

        tile_painter.end()
        return pixmap

    def invalidate_tiles(self) -> None:
        """Call if the underlying road graph is ever reloaded at runtime
        (e.g. a fresh car-drive sync) — otherwise stale cached tiles (and
        the stale spatial edge index) from the old data would keep being
        reused for the rest of the session."""
        global _edge_grid_cache
        _edge_grid_cache = None
        self._tile_cache.clear()
        self.update()

    def _draw_route(self, painter: QPainter) -> None:
        path = QPainterPath()
        pts = [self._to_screen(e, n) for e, n in self._route_points]
        if not pts:
            return
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        painter.setPen(QPen(QColor(ACCENT), 7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)

    def _draw_places(self, painter: QPainter) -> None:
        # Plain dots, not emoji-in-a-circle: drawText() with a font lookup
        # is real per-call overhead in Qt, and with a real extract's POI
        # count (versus the handful in the old synthetic seed data) that
        # overhead multiplied by every visible place was a big chunk of the
        # "everything is slow" feeling. A dot is one drawEllipse() call.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(ACCENT)))
        for place in self._places:
            node = GRAPH.nodes.get(place.node_id)
            if node is None:
                continue
            pt = self._to_screen(node.east, node.north)
            painter.drawEllipse(pt, 5, 5)

    def _draw_user(self, painter: QPainter) -> None:
        pt = self._to_screen(*self._user_pos)
        glow = QColor(ACCENT)
        glow.setAlpha(60)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(pt, 22, 22)

        if self._nav_mode:
            arrow = QPolygonF(
                [
                    QPointF(0, -16),
                    QPointF(11, 11),
                    QPointF(0, 4),
                    QPointF(-11, 11),
                ]
            )
            painter.save()
            painter.translate(pt)
            if not self._follow_mode:
                # While following, paintEvent has already rotated the
                # whole scene so heading points up — a fixed "points up"
                # shape is correct as-is. Once panned/zoomed away, that
                # global rotation stops (see paintEvent), so the arrow has
                # to rotate itself to still point the right way in a
                # normal north-up view.
                painter.rotate(self._heading)
            painter.setPen(QPen(QColor("white"), 2))
            painter.setBrush(QBrush(QColor(ACCENT)))
            painter.drawPolygon(arrow)
            painter.restore()
        else:
            painter.setPen(QPen(QColor("white"), 3))
            painter.setBrush(QBrush(QColor(ACCENT)))
            painter.drawEllipse(pt, 9, 9)
