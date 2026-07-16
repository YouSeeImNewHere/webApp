from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..geo.routing import RouteOption, path_points, point_and_heading_at_fraction
from ..geo.search_db import Place
from ..widgets.map_canvas import MapCanvas

STEP_INTERVAL_MS = 4000

# Genuine street-level zoom — just the current road and its immediate
# intersections, not several blocks of context. This used to be clamped to
# whatever the app's old zoom ceiling allowed regardless of what was
# requested here (see MAX_SCALE in map_canvas.py) — now that the ceiling
# itself is high enough, this value actually takes effect.
NAV_VIEW_RADIUS_M = 45.0


class NavScreen(QWidget):
    end_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._place: Place | None = None
        self._route: RouteOption | None = None
        self._steps: list = []
        self._route_points: list[tuple[float, float]] = []
        self._total_distance_m = 0.0
        self._step_index = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_step)

        base = QGridLayout(self)
        base.setContentsMargins(0, 0, 0, 0)

        self.map_bg = MapCanvas()
        base.addWidget(self.map_bg, 0, 0)

        content = QWidget()
        base.addWidget(content, 0, 0)
        content.raise_()

        root = QVBoxLayout(content)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        banner = QWidget()
        banner.setObjectName("navBanner")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(20, 20, 20, 20)
        banner_layout.setSpacing(18)

        self.maneuver_label = QLabel("↑")
        self.maneuver_label.setObjectName("navManeuverIcon")
        self.maneuver_label.setFixedSize(64, 64)
        self.maneuver_label.setAlignment(Qt.AlignCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        self.instruction_label = QLabel("Head north on Main St")
        self.instruction_label.setProperty("role", "navInstruction")
        self.instruction_label.setWordWrap(True)
        self.distance_label = QLabel("in 0.4 mi")
        self.distance_label.setProperty("role", "navDistance")
        text_col.addWidget(self.instruction_label)
        text_col.addWidget(self.distance_label)

        banner_layout.addWidget(self.maneuver_label)
        banner_layout.addLayout(text_col, 1)
        root.addWidget(banner)

        self.next_label = QLabel("")
        self.next_label.setProperty("role", "dimLabel")
        self.next_label.setContentsMargins(16, 4, 16, 0)
        root.addWidget(self.next_label)

        zoom_row = QHBoxLayout()
        zoom_row.addStretch(1)
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setProperty("role", "iconButton")
        zoom_in_btn.setFixedSize(48, 48)
        zoom_in_btn.setCursor(Qt.PointingHandCursor)
        zoom_in_btn.clicked.connect(self.map_bg.zoom_in)
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setProperty("role", "iconButton")
        zoom_out_btn.setFixedSize(48, 48)
        zoom_out_btn.setCursor(Qt.PointingHandCursor)
        zoom_out_btn.clicked.connect(self.map_bg.zoom_out)
        zoom_row.addWidget(zoom_in_btn)
        zoom_row.addWidget(zoom_out_btn)
        root.addLayout(zoom_row)

        root.addStretch(1)

        self.arrived_btn = QPushButton("I've Arrived")
        self.arrived_btn.setObjectName("arrivedButton")
        self.arrived_btn.setMinimumHeight(72)
        self.arrived_btn.setMinimumWidth(260)
        self.arrived_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.arrived_btn.setCursor(Qt.PointingHandCursor)
        self.arrived_btn.clicked.connect(self.end_requested.emit)
        self.arrived_btn.hide()

        arrived_row = QHBoxLayout()
        arrived_row.addStretch(1)
        arrived_row.addWidget(self.arrived_btn)
        arrived_row.addStretch(1)
        root.addLayout(arrived_row)

        bottom = QWidget()
        bottom.setObjectName("navBottomBar")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(22, 14, 22, 14)
        bottom_layout.setSpacing(20)

        eta_col = QVBoxLayout()
        eta_col.setSpacing(2)
        self.eta_label = QLabel("--:--")
        self.eta_label.setProperty("role", "navEta")
        eta_caption = QLabel("ETA")
        eta_caption.setProperty("role", "dimLabel")
        eta_col.addWidget(self.eta_label)
        eta_col.addWidget(eta_caption)

        self.remaining_label = QLabel("-- min · -- mi")
        self.remaining_label.setProperty("role", "dimLabel")

        end_btn = QPushButton("End")
        end_btn.setObjectName("navEndButton")
        end_btn.setMinimumHeight(56)
        end_btn.setCursor(Qt.PointingHandCursor)
        end_btn.clicked.connect(self.end_requested.emit)

        bottom_layout.addLayout(eta_col)
        bottom_layout.addWidget(self.remaining_label, 1)
        bottom_layout.addWidget(end_btn)
        root.addWidget(bottom)

    def start(self, place: Place, route: RouteOption):
        self._place = place
        self._route = route
        self._steps = route.steps
        self._route_points = path_points(route.path)
        self._total_distance_m = sum(s.distance_m for s in self._steps)
        self._step_index = 0
        self.arrived_btn.hide()

        self.map_bg.set_route(self._route_points)
        self.map_bg.set_nav_mode(True)
        if self._route_points:
            self.map_bg.center_on_with_radius(*self._route_points[0], NAV_VIEW_RADIUS_M)

        self._render_step()
        self._timer.start(STEP_INTERVAL_MS)

    def stop(self):
        self._timer.stop()
        self.map_bg.clear_route()
        self.map_bg.set_nav_mode(False)

    def _render_step(self):
        step = self._steps[self._step_index]
        has_next = self._step_index + 1 < len(self._steps)
        next_step = self._steps[self._step_index + 1] if has_next else None

        self.maneuver_label.setText(step.maneuver)
        self.instruction_label.setText(step.instruction)
        self.distance_label.setText(
            f"in {step.distance_m / 1609.34:.1f} mi" if step.distance_m > 0 else "Arriving now"
        )
        self.next_label.setText(f"Then: {next_step.instruction}" if next_step else "")

        completed_m = sum(s.distance_m for s in self._steps[: self._step_index])
        remaining_m = max(0.0, self._total_distance_m - completed_m)
        fraction_done = completed_m / self._total_distance_m if self._total_distance_m else 1.0
        minutes_left = max(0, round(self._route.minutes * (1 - fraction_done)))
        eta = datetime.now() + timedelta(minutes=minutes_left)
        self.eta_label.setText(eta.strftime("%-I:%M %p"))
        self.remaining_label.setText(f"{minutes_left} min · {remaining_m / 1609.34:.1f} mi")

        point, heading = point_and_heading_at_fraction(self._route_points, fraction_done)
        self.map_bg.set_user_position(*point)
        self.map_bg.set_heading(heading)
        self.map_bg.center_on(*point)

        self.arrived_btn.setVisible(self._step_index >= len(self._steps) - 1)

    def _advance_step(self):
        if self._step_index >= len(self._steps) - 1:
            self._timer.stop()
            return
        self._step_index += 1
        self._render_step()
