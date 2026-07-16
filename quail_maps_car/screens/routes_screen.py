from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..geo.routing import RouteOption, compute_routes
from ..geo.search_db import Place
from ..theme import (
    BORDER,
    DIM_TEXT_STYLE,
    ROUTE_ARRIVAL_TIME_STYLE,
    ROUTE_CARD_SELECTED_STYLE,
    ROUTE_CARD_STYLE,
    ROUTE_DURATION_STYLE,
    ROUTE_RANK_SELECTED_STYLE,
    ROUTE_RANK_STYLE,
    SURFACE,
)
from ..widgets.clickable import ClickableWidget


class _RouteWorker(QThread):
    """compute_routes() now does adaptive bbox-widening SQL queries against
    the full real extract (can be a multi-million-row file) plus a Dijkstra
    connectivity check per widening attempt — genuinely slow enough on the
    mini PC's weak CPU to look exactly like a hang if it runs on the UI
    thread, which is what "python3 not responding" actually was. Runs the
    computation here instead so the UI stays responsive and can show a
    loading state instead of appearing frozen."""

    routes_ready = Signal(list)

    def __init__(self, start_id: str, goal_id: str, parent=None):
        super().__init__(parent)
        self._start_id = start_id
        self._goal_id = goal_id

    def run(self):
        try:
            routes = compute_routes(self._start_id, self._goal_id)
        except Exception:
            routes = []
        self.routes_ready.emit(routes)


class RoutesScreen(QWidget):
    """A bottom-sheet overlay (same pattern as PlaceDetailScreen), not a
    full page — hosted directly in MainWindow layered above the screen
    stack so it works the same whether it was opened from the Idle
    shortcuts or from Search's place-detail overlay, without covering
    whatever's behind it."""

    back_requested = Signal()
    start_drive_requested = Signal(object, object)  # Place, RouteOption

    def __init__(self, parent=None):
        super().__init__(parent)
        self._place: Place | None = None
        self._routes: list[RouteOption] = []
        self._selected_index = 0
        self._worker: _RouteWorker | None = None
        self._request_token = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        card = QWidget()
        card.setObjectName("routesCard")
        card.setStyleSheet(
            f"""
            #routesCard {{
                background-color: {SURFACE};
                border-top-left-radius: 24px;
                border-top-right-radius: 24px;
                border: 1px solid {BORDER};
            }}
            """
        )
        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(14)

        back_btn = QPushButton("✕")
        back_btn.setProperty("role", "iconButton")
        back_btn.setFixedSize(56, 56)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back_requested.emit)

        self.destination_label = QLabel("Destination")
        self.destination_label.setProperty("role", "routesDestination")

        header_layout.addWidget(back_btn)
        header_layout.addWidget(self.destination_label, 1)
        root.addWidget(header)

        self.route_list_layout = QVBoxLayout()
        self.route_list_layout.setSpacing(10)
        route_list_container = QWidget()
        route_list_container.setLayout(self.route_list_layout)

        route_scroll = QScrollArea()
        route_scroll.setWidgetResizable(True)
        route_scroll.setFrameShape(QScrollArea.NoFrame)
        route_scroll.setMinimumHeight(260)
        route_scroll.setMaximumHeight(320)
        route_scroll.setStyleSheet("background: transparent; border: none;")
        route_scroll.viewport().setStyleSheet("background: transparent;")
        route_list_container.setStyleSheet("background: transparent;")
        route_scroll.setWidget(route_list_container)

        route_wrap = QWidget()
        route_wrap_layout = QVBoxLayout(route_wrap)
        route_wrap_layout.setContentsMargins(20, 0, 20, 0)
        route_wrap_layout.addWidget(route_scroll)
        root.addWidget(route_wrap)

        self.start_btn = QPushButton("Start Drive")
        self.start_btn.setObjectName("startNavButton")
        self.start_btn.setMinimumHeight(72)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._start_drive)

        start_wrap = QWidget()
        start_wrap_layout = QVBoxLayout(start_wrap)
        start_wrap_layout.setContentsMargins(20, 16, 20, 20)
        start_wrap_layout.addWidget(self.start_btn)
        root.addWidget(start_wrap)

    def paintEvent(self, event):
        # Dims whatever's behind this overlay instead of covering it with
        # an opaque background — same treatment as PlaceDetailScreen.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))
        super().paintEvent(event)

    def open_for(self, place: Place):
        self._place = place
        self._routes = []
        self._selected_index = 0
        self.destination_label.setText(place.name)
        self._show_loading()
        self.show()
        self.raise_()

        self._request_token += 1
        token = self._request_token
        worker = _RouteWorker("START", place.node_id, self)
        worker.routes_ready.connect(lambda routes: self._on_routes_ready(token, routes))
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _show_loading(self):
        while self.route_list_layout.count():
            item = self.route_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        self.start_btn.setEnabled(False)
        loading = QLabel("Finding route…")
        loading.setStyleSheet(DIM_TEXT_STYLE)
        loading.setAlignment(Qt.AlignCenter)
        self.route_list_layout.addWidget(loading)
        self.route_list_layout.addStretch(1)

    def _on_routes_ready(self, token: int, routes: list[RouteOption]):
        # A second tap (a different destination, or reopening this one)
        # before the first request finished would otherwise let a slower,
        # stale result clobber whatever the newer request found.
        if token != self._request_token:
            return
        self._routes = routes
        self._selected_index = 0
        self._render_routes()

    def _render_routes(self):
        while self.route_list_layout.count():
            item = self.route_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()

        self.start_btn.setEnabled(bool(self._routes))

        if not self._routes:
            # compute_routes() can legitimately come back empty — most
            # likely the destination is outside the loaded road graph's
            # radius (roadnet.py bounds it to 3mi for load performance).
            # This used to fail completely silently: _start_drive() just
            # returned early with nothing shown, so pressing "Start Drive"
            # looked like the button was simply broken.
            empty = QLabel("No route found. This destination may be outside your loaded map area.")
            empty.setStyleSheet(DIM_TEXT_STYLE)
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignCenter)
            self.route_list_layout.addWidget(empty)
            self.route_list_layout.addStretch(1)
            return

        now = datetime.now()
        for index, route in enumerate(self._routes):
            arrival = now + timedelta(minutes=route.minutes)

            selected = index == self._selected_index

            card = ClickableWidget()
            card.setStyleSheet(ROUTE_CARD_SELECTED_STYLE if selected else ROUTE_CARD_STYLE)
            card.setMinimumHeight(76)
            card.setCursor(Qt.PointingHandCursor)

            layout = QHBoxLayout(card)
            layout.setContentsMargins(16, 12, 16, 12)
            layout.setSpacing(14)

            rank = QLabel(str(index + 1))
            rank.setStyleSheet(ROUTE_RANK_SELECTED_STYLE if selected else ROUTE_RANK_STYLE)
            rank.setFixedSize(30, 30)
            rank.setAlignment(Qt.AlignCenter)

            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            duration = QLabel(f"{route.minutes} min")
            duration.setStyleSheet(ROUTE_DURATION_STYLE)
            meta = QLabel(f"{route.label} · {route.distance_mi:.1f} mi via {route.via}")
            meta.setStyleSheet(DIM_TEXT_STYLE)
            info_col.addWidget(duration)
            info_col.addWidget(meta)

            arrival_col = QVBoxLayout()
            arrival_col.setSpacing(2)
            arrival_time = QLabel(arrival.strftime("%-I:%M %p"))
            arrival_time.setStyleSheet(ROUTE_ARRIVAL_TIME_STYLE)
            arrival_time.setAlignment(Qt.AlignRight)
            arrival_label = QLabel("ETA")
            arrival_label.setStyleSheet(DIM_TEXT_STYLE)
            arrival_label.setAlignment(Qt.AlignRight)
            arrival_col.addWidget(arrival_time)
            arrival_col.addWidget(arrival_label)

            layout.addWidget(rank)
            layout.addLayout(info_col, 1)
            layout.addLayout(arrival_col)

            card.clicked.connect(lambda i=index: self._select_route(i))
            self.route_list_layout.addWidget(card)
        self.route_list_layout.addStretch(1)

    def _select_route(self, index: int):
        self._selected_index = index
        self._render_routes()

    def _start_drive(self):
        if self._place is None or not self._routes:
            return
        self.start_drive_requested.emit(self._place, self._routes[self._selected_index])
