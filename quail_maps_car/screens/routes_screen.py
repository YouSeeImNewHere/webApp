from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal
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
    DIM_TEXT_STYLE,
    ROUTE_ARRIVAL_TIME_STYLE,
    ROUTE_CARD_SELECTED_STYLE,
    ROUTE_CARD_STYLE,
    ROUTE_DURATION_STYLE,
    ROUTE_RANK_SELECTED_STYLE,
    ROUTE_RANK_STYLE,
)
from ..widgets.clickable import ClickableWidget
from ..widgets.opaque_screen import OpaqueScreen


class RoutesScreen(OpaqueScreen):
    back_requested = Signal()
    start_drive_requested = Signal(object, object)  # Place, RouteOption

    def __init__(self, parent=None):
        super().__init__(parent)
        self._place: Place | None = None
        self._routes: list[RouteOption] = []
        self._selected_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addStretch(1)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(14)

        back_btn = QPushButton("←")
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

    def open_for(self, place: Place):
        self._place = place
        self._routes = compute_routes("START", place.node_id)
        self._selected_index = 0
        self.destination_label.setText(place.name)
        self._render_routes()

    def _render_routes(self):
        while self.route_list_layout.count():
            item = self.route_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()

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
