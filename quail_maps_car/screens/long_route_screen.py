"""In-app screen for a Valhalla long-distance route preview (see
valhalla_client.py), replacing the native QMessageBox dialog that used to
show this - a real user complaint: a popup dialog doesn't look/feel like
part of the app the way every other screen does.

This is still a preview, not full live navigation: the route's shape is
drawn as a simple schematic line (min/max-normalized to fit the widget),
not overlaid on real road tiles - map_canvas.py's renderer only has data
for whatever's in the one locally-downloaded extract, nowhere close to
enough to render an accurate basemap under a cross-country line. Drawing
the shape unscaled against that renderer would be actively misleading
(implying road-accurate positioning that isn't there), so this is
deliberately presented as a route overview + turn list, not a live map."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..geo.valhalla_client import LongRoute
from ..theme import ACCENT, BG, BORDER, DIM_TEXT_STYLE, SURFACE, SURFACE_RAISED, TEXT


class _RouteShapeCanvas(QWidget):
    """A schematic (not to-scale-with-roads) line plot of the route's
    decoded shape - see this module's docstring for why it's deliberately
    not drawn against the real road-tile map."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list[tuple[float, float]] = []  # (lat, lon)
        self.setMinimumHeight(220)

    def set_shape(self, shape: list[tuple[float, float]]) -> None:
        # Thinning keeps paintEvent cheap - a cross-country route can decode
        # to 20k+ points, and this is a rough overview, not a precise path.
        step = max(1, len(shape) // 2000)
        self._points = shape[::step]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(BG))
        if len(self._points) < 2:
            return

        lats = [p[0] for p in self._points]
        lons = [p[1] for p in self._points]
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        lat_span = max(lat_max - lat_min, 1e-6)
        lon_span = max(lon_max - lon_min, 1e-6)

        margin = 24.0
        w = self.width() - 2 * margin
        h = self.height() - 2 * margin

        def to_widget(lat: float, lon: float) -> tuple[float, float]:
            x = margin + (lon - lon_min) / lon_span * w
            y = margin + (1.0 - (lat - lat_min) / lat_span) * h  # north is up
            return x, y

        path = QPainterPath()
        x0, y0 = to_widget(*self._points[0])
        path.moveTo(x0, y0)
        for lat, lon in self._points[1:]:
            path.lineTo(*to_widget(lat, lon))

        painter.setPen(QPen(QColor(ACCENT), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)

        for lat, lon, color in ((self._points[0][0], self._points[0][1], "#34c759"), (self._points[-1][0], self._points[-1][1], "#ff453a")):
            x, y = to_widget(lat, lon)
            painter.setBrush(QColor(color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(x, y), 6, 6)


class LongRouteScreen(QWidget):
    """Full-screen route preview, pushed onto MainWindow's stack like any
    other screen (Search, Nav, etc.) instead of a modal dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG};")
        self._on_back = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(20, 16, 20, 8)
        back_btn = QPushButton("←")
        back_btn.setProperty("role", "iconButton")
        back_btn.setFixedSize(64, 64)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self._handle_back)
        self.title_label = QLabel("Route")
        self.title_label.setStyleSheet(f"color: {TEXT}; font-size: 20px; font-weight: 800;")
        bar_layout.addWidget(back_btn)
        bar_layout.addWidget(self.title_label, 1)
        root.addWidget(bar)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(f"color: {TEXT}; font-size: 17px; font-weight: 700; padding: 0 24px;")
        root.addWidget(self.summary_label)

        note = QLabel("Overview only — live turn-by-turn only works within a downloaded area.")
        note.setStyleSheet(DIM_TEXT_STYLE + " padding: 4px 24px 12px 24px;")
        root.addWidget(note)

        self.canvas = _RouteShapeCanvas()
        self.canvas.setStyleSheet(f"border: 1px solid {BORDER}; border-radius: 12px; margin: 0 20px;")
        root.addWidget(self.canvas)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        self.steps_inner = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_inner)
        self.steps_layout.setContentsMargins(20, 12, 20, 20)
        self.steps_layout.setSpacing(8)
        scroll.setWidget(self.steps_inner)
        root.addWidget(scroll, 1)

    def set_on_back(self, callback) -> None:
        self._on_back = callback

    def _handle_back(self) -> None:
        if self._on_back:
            self._on_back()

    def show_route(self, name: str, route: LongRoute) -> None:
        self.title_label.setText(f"Route to {name}")
        hours, minutes = divmod(route.minutes, 60)
        self.summary_label.setText(f"{route.distance_mi:.0f} miles · about {hours}h {minutes}m")
        self.canvas.set_shape(route.shape)

        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for step in route.steps:
            row = QWidget()
            row.setStyleSheet(f"background-color: {SURFACE_RAISED}; border-radius: 10px;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)
            glyph = QLabel(step.maneuver)
            glyph.setStyleSheet(f"color: {ACCENT}; font-size: 18px; font-weight: 800;")
            glyph.setFixedWidth(28)
            text = QLabel(step.instruction)
            text.setStyleSheet(f"color: {TEXT}; font-size: 15px;")
            text.setWordWrap(True)
            dist = QLabel(f"{step.distance_m / 1609.34:.1f} mi" if step.distance_m > 0 else "")
            dist.setStyleSheet(DIM_TEXT_STYLE)
            row_layout.addWidget(glyph)
            row_layout.addWidget(text, 1)
            row_layout.addWidget(dist)
            self.steps_layout.addWidget(row)
