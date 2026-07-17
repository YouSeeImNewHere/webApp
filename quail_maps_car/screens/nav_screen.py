from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..geo.routing import RouteOption, fraction_at_nearest_point, path_points, point_and_heading_at_fraction
from ..geo.search_db import Place
from ..widgets.map_canvas import MapCanvas

# Genuine street-level zoom — just the current road and its immediate
# intersections, not several blocks of context. This used to be clamped to
# whatever the app's old zoom ceiling allowed regardless of what was
# requested here (see MAX_SCALE in map_canvas.py) — now that the ceiling
# itself is high enough, this value actually takes effect.
NAV_VIEW_RADIUS_M = 45.0


class NavScreen(QWidget):
    end_requested = Signal()
    # (east, north, heading_deg, eta_min, remaining_mi) — local-frame
    # position each step tick, for MainWindow to forward to
    # BluetoothCarLink.send_position() (converted to lat/lon there) when a
    # phone is connected. Emitted unconditionally regardless of whether
    # anything's listening — cheap, and keeps this screen's rendering
    # logic and the car-link wiring in main_window.py fully decoupled.
    position_updated = Signal(float, float, float, int, float)
    # (maneuver glyph, instruction text, distance-to-turn text, eta text) —
    # everything DashboardScreen's next-turn card needs to mirror the nav
    # banner, without it having to know about RouteOption/TurnStep at all.
    instruction_updated = Signal(str, str, str, str)
    # Fired from stop() so anything mirroring live nav state elsewhere
    # (the dashboard's next-turn card) knows to clear/hide itself.
    navigation_stopped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._place: Place | None = None
        self._route: RouteOption | None = None
        self._steps: list = []
        self._route_points: list[tuple[float, float]] = []
        self._total_distance_m = 0.0
        self._step_index = 0

        base = QGridLayout(self)
        base.setContentsMargins(0, 0, 0, 0)

        self.map_bg = MapCanvas()
        base.addWidget(self.map_bg, 0, 0)

        # `content` used to be a SIBLING of map_bg in this same grid cell
        # (base.addWidget(content, 0, 0) + raise_()) — that's the actual
        # reason pan/pinch/tap never reached the map at all: a plain
        # widget blocks mouse/touch input across its entire area, and
        # WA_TransparentForMouseEvents does NOT pass clicks through to a
        # sibling stacked underneath in a shared layout cell (verified —
        # tried exactly that first, it does not work). It only passes
        # clicks through to an actual PARENT, so `content` now has to be a
        # genuine child of map_bg (added via a layout set directly on
        # map_bg itself, not the outer grid) for the empty background to
        # be click/touch-transparent while buttons inside it stay
        # interactive — confirmed with an isolated test before wiring this
        # into the real screens.
        content = QWidget()
        content.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        map_bg_layout = QVBoxLayout(self.map_bg)
        map_bg_layout.setContentsMargins(0, 0, 0, 0)
        map_bg_layout.addWidget(content)

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

        # Shown only while the user has panned/zoomed away from the car
        # (see MapCanvas.follow_mode_changed) — tapping it resumes the
        # heading-up follow camera.
        self.recenter_btn = QPushButton("⟲ Recenter")
        self.recenter_btn.setProperty("role", "iconButton")
        self.recenter_btn.setFixedHeight(48)
        self.recenter_btn.setCursor(Qt.PointingHandCursor)
        self.recenter_btn.clicked.connect(self.map_bg.recenter)
        self.recenter_btn.hide()
        zoom_row.addWidget(self.recenter_btn)

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

        self.map_bg.follow_mode_changed.connect(lambda following: self.recenter_btn.setVisible(not following))

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
        # Reset on every new drive — otherwise a locally-started drive
        # right after a phone-triggered one would inherit a stale override
        # from the previous trip.
        self._minutes_override: int | None = None
        self._distance_mi_override: float | None = None
        self.arrived_btn.hide()

        self.recenter_btn.hide()
        self.map_bg.set_route(self._route_points)
        # set_nav_mode(True) also resets follow mode on — needed in case a
        # previous drive on this same MapCanvas instance ended with follow
        # paused (user had panned away right before tapping "I've Arrived").
        self.map_bg.set_nav_mode(True)
        if self._route_points:
            self.map_bg.center_on_with_radius(*self._route_points[0], NAV_VIEW_RADIUS_M)

        self._render_at_fraction(0.0)

    def stop(self):
        self.map_bg.clear_route()
        self.map_bg.set_nav_mode(False)
        self.recenter_btn.hide()
        self.navigation_stopped.emit()

    def set_display_overrides(self, minutes: int, distance_mi: float) -> None:
        """Substitutes the phone's own already-computed route numbers for
        the car's, in the ETA/remaining-distance display only — the car
        still drives its own actual path/steps (real turn-by-turn needs
        the car's own road graph regardless), this just stops the two
        screens from showing two different arrival times for what the
        driver thinks is the same drive."""
        self._minutes_override = minutes
        self._distance_mi_override = distance_mi
        # Always called right after start() (still at fraction 0) — see
        # main_window.py's _start_navigation().
        self._render_at_fraction(0.0)

    def update_from_real_position(self, east: float, north: float) -> None:
        """Advances nav progress off a real position fix — from the phone's
        GPS, forwarded over BluetoothCarLink — instead of the old
        QTimer-driven simulation that pushed progress forward on a fixed
        clock regardless of whether the car was actually moving at all."""
        if not self._route_points or self._total_distance_m <= 0:
            return
        fraction = fraction_at_nearest_point(self._route_points, east, north)
        self._render_at_fraction(fraction)

    def _step_index_for_fraction(self, fraction_done: float) -> int:
        completed_m = fraction_done * self._total_distance_m
        acc = 0.0
        for i, step in enumerate(self._steps):
            acc += step.distance_m
            if completed_m <= acc or i == len(self._steps) - 1:
                return i
        return len(self._steps) - 1

    def _render_at_fraction(self, fraction_done: float) -> None:
        fraction_done = max(0.0, min(1.0, fraction_done))
        self._step_index = self._step_index_for_fraction(fraction_done)
        step = self._steps[self._step_index]
        has_next = self._step_index + 1 < len(self._steps)
        next_step = self._steps[self._step_index + 1] if has_next else None

        self.maneuver_label.setText(step.maneuver)
        self.instruction_label.setText(step.instruction)
        self.distance_label.setText(
            f"in {step.distance_m / 1609.34:.1f} mi" if step.distance_m > 0 else "Arriving now"
        )
        self.next_label.setText(f"Then: {next_step.instruction}" if next_step else "")

        # When set, these are the phone's own already-computed numbers
        # (see set_display_overrides()) — used here in place of the car's
        # own route.minutes/total_distance_m so the two screens agree.
        total_minutes = self._minutes_override if self._minutes_override is not None else self._route.minutes
        total_distance_mi = (
            self._distance_mi_override if self._distance_mi_override is not None
            else self._total_distance_m / 1609.34
        )
        remaining_mi = max(0.0, total_distance_mi * (1 - fraction_done))
        minutes_left = max(0, round(total_minutes * (1 - fraction_done)))
        eta = datetime.now() + timedelta(minutes=minutes_left)
        self.eta_label.setText(eta.strftime("%-I:%M %p"))
        self.remaining_label.setText(f"{minutes_left} min · {remaining_mi:.1f} mi")

        point, heading = point_and_heading_at_fraction(self._route_points, fraction_done)
        self.map_bg.follow(*point, heading)
        self.position_updated.emit(point[0], point[1], heading, minutes_left, remaining_mi)
        self.instruction_updated.emit(
            step.maneuver, step.instruction, self.distance_label.text(), self.eta_label.text(),
        )

        self.arrived_btn.setVisible(self._step_index >= len(self._steps) - 1)
