from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from ..geo.roadnet import GRAPH
from ..geo.search_db import Place
from ..theme import ACCENT

MIN_SCALE = 0.02
MAX_SCALE = 0.6


class MapCanvas(QWidget):
    """Renders the local road graph with real QPainter drawing: no tiles,
    no web view — roads, POIs, the active route, and the user's position
    are all drawn directly from the routing graph's own coordinates. Pan
    with drag, zoom with the scroll wheel or the +/- buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._center = (0.0, 0.0)
        self._scale = 0.1  # pixels per meter
        self._places: list[Place] = []
        self._route_points: list[tuple[float, float]] = []
        self._user_pos = (0.0, 0.0)
        self._dragging = False
        self._drag_last: QPointF | None = None

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

    def center_on(self, east: float, north: float) -> None:
        self._center = (east, north)
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
        self._scale = min(MAX_SCALE, self._scale * 1.3)
        self.update()

    def zoom_out(self) -> None:
        self._scale = max(MIN_SCALE, self._scale / 1.3)
        self.update()

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

    # ---- painting ----

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0a0d13"))

        self._draw_roads(painter)
        if self._route_points:
            self._draw_route(painter)
        self._draw_places(painter)
        self._draw_user(painter)

    def _draw_roads(self, painter: QPainter) -> None:
        for edge in GRAPH.edges:
            a = GRAPH.nodes[edge.a]
            b = GRAPH.nodes[edge.b]
            p1 = self._to_screen(a.east, a.north)
            p2 = self._to_screen(b.east, b.north)
            if edge.road_class == "highway":
                pen = QPen(QColor("#3a4356"), 6, Qt.SolidLine, Qt.RoundCap)
            else:
                pen = QPen(QColor("#242c3a"), 4, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(p1, p2)

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
        font = QFont()
        font.setPixelSize(13)
        painter.setFont(font)
        for place in self._places:
            node = GRAPH.nodes[place.node_id]
            pt = self._to_screen(node.east, node.north)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#171c26")))
            painter.drawEllipse(pt, 13, 13)
            painter.setPen(QPen(QColor("#f4f6fa")))
            painter.drawText(QRectF(pt.x() - 13, pt.y() - 13, 26, 26), Qt.AlignCenter, place.icon)

    def _draw_user(self, painter: QPainter) -> None:
        pt = self._to_screen(*self._user_pos)
        glow = QColor(ACCENT)
        glow.setAlpha(60)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(pt, 22, 22)
        painter.setPen(QPen(QColor("white"), 3))
        painter.setBrush(QBrush(QColor(ACCENT)))
        painter.drawEllipse(pt, 9, 9)
