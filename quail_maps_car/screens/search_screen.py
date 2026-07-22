from __future__ import annotations

from PySide6.QtCore import QThread, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..geo.latlon import haversine_mi
from ..geo.remote_search import RemotePlace, fetch_remote_cities, fetch_remote_places
from ..geo.search_db import Place, fetch_places
from ..theme import DIM_TEXT_STYLE, RESULT_ICON_STYLE, RESULT_NAME_STYLE, RESULT_ROW_STYLE
from ..widgets.clickable import ClickableWidget
from ..widgets.opaque_screen import OpaqueScreen
from .place_detail_screen import PlaceDetailScreen

# How long to wait after the user stops typing before hitting the network -
# the local (offline, instant) results already refresh on every keystroke;
# this just avoids firing a request per keystroke for the remote search.
_REMOTE_SEARCH_DEBOUNCE_MS = 500


class _RemoteSearchWorker(QThread):
    """Two real network calls to homelab (see remote_search.py) - off the
    UI thread for the same reason RoutesScreen's local route computation
    is, just for network latency instead of CPU time."""

    results_ready = Signal(list, int)  # list[RemotePlace], request token

    def __init__(self, query: str, latlon: tuple[float, float] | None, token: int, parent=None):
        super().__init__(parent)
        self._query = query
        self._latlon = latlon
        self._token = token

    def run(self):
        results: list[RemotePlace] = []
        try:
            results.extend(fetch_remote_cities(self._query))
            if self._latlon is not None:
                lat, lon = self._latlon
                results.extend(fetch_remote_places(self._query, lat, lon))
        except Exception:
            pass
        self.results_ready.emit(results, self._token)

# Building a real Qt widget (icon + two labels) per result is real
# per-row cost — against a real extract's POI count (versus a handful in
# the old synthetic seed data), rendering every match unconditionally was
# a big part of the app feeling slow to use. Nobody scrolls through
# hundreds of results in a car anyway.
_MAX_RESULTS = 40


class SearchScreen(OpaqueScreen):
    back_requested = Signal()
    place_selected = Signal(object)  # emitted once "Drive" is picked from the detail overlay

    def __init__(self, parent=None):
        super().__init__(parent)
        self._category_filter: str | None = None
        self._current_latlon: tuple[float, float] | None = None
        self._remote_debounce = QTimer(self)
        self._remote_debounce.setSingleShot(True)
        self._remote_debounce.timeout.connect(self._run_remote_search)
        self._remote_worker: _RemoteSearchWorker | None = None
        self._remote_token = 0
        self._remote_rows: list[Place] = []

        # Grid instead of a single vbox so the place-detail overlay can
        # occupy the same cell, layered on top — it used to be a separate
        # full page in the app's screen stack, which meant it visually
        # replaced everything instead of appearing as a bottom sheet over
        # the results still behind it.
        base = QGridLayout(self)
        base.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        base.addWidget(content, 0, 0)

        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(20, 16, 20, 16)
        bar_layout.setSpacing(12)

        back_btn = QPushButton("←")
        back_btn.setProperty("role", "iconButton")
        back_btn.setFixedSize(64, 64)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back_requested.emit)

        self.input = QLineEdit()
        self.input.setObjectName("searchInput")
        self.input.setMinimumHeight(64)
        self.input.setPlaceholderText("Search offline places or address")
        self.input.textChanged.connect(self._refresh_results)

        mic_btn = QPushButton("\U0001f3a4")
        mic_btn.setProperty("role", "iconButton")
        mic_btn.setFixedSize(64, 64)
        mic_btn.setCursor(Qt.PointingHandCursor)

        bar_layout.addWidget(back_btn)
        bar_layout.addWidget(self.input, 1)
        bar_layout.addWidget(mic_btn)
        root.addWidget(bar)

        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setFrameShape(QScrollArea.NoFrame)
        self.results_scroll.setStyleSheet("background: transparent; border: none;")
        self.results_scroll.viewport().setStyleSheet("background: transparent;")
        self.results_inner = QWidget()
        self.results_inner.setStyleSheet("background: transparent;")
        self.results_layout = QVBoxLayout(self.results_inner)
        self.results_layout.setContentsMargins(20, 4, 20, 20)
        self.results_layout.setSpacing(0)
        self.results_scroll.setWidget(self.results_inner)
        root.addWidget(self.results_scroll, 1)

        self.detail_overlay = PlaceDetailScreen()
        self.detail_overlay.hide()
        self.detail_overlay.back_requested.connect(self.detail_overlay.hide)
        self.detail_overlay.drive_requested.connect(self._on_drive_requested)
        base.addWidget(self.detail_overlay, 0, 0)
        self.detail_overlay.raise_()

    def open_for(self, category: str | None):
        self._category_filter = category
        self.input.blockSignals(True)
        self.input.clear()
        self.input.blockSignals(False)
        self.detail_overlay.hide()
        self._remote_rows = []
        self._refresh_results()
        self.input.setFocus()

    def set_current_position(self, lat: float, lon: float) -> None:
        self._current_latlon = (lat, lon)

    def _on_drive_requested(self, place: Place):
        self.detail_overlay.hide()
        self.place_selected.emit(place)

    def _refresh_results(self):
        query = self.input.text()
        # A new query invalidates any remote results still in flight or
        # already shown from the previous query - bumping the token means
        # _on_remote_results ignores a stale worker's results if it lands
        # after the user kept typing.
        self._remote_token += 1
        self._remote_rows = []
        self._remote_debounce.stop()
        if query.strip():
            self._remote_debounce.start(_REMOTE_SEARCH_DEBOUNCE_MS)
        self._render_results(query)

    def _run_remote_search(self):
        query = self.input.text().strip()
        if not query:
            return
        worker = _RemoteSearchWorker(query, self._current_latlon, self._remote_token)
        worker.results_ready.connect(self._on_remote_results)
        self._remote_worker = worker
        worker.start()

    def _on_remote_results(self, remote_places: list[RemotePlace], token: int):
        if token != self._remote_token:
            return  # query changed since this search was kicked off
        self._remote_rows = [self._to_place(p) for p in remote_places]
        self._render_results(self.input.text())

    def _to_place(self, remote: RemotePlace) -> Place:
        distance_mi = 0.0
        if self._current_latlon is not None:
            distance_mi = haversine_mi(*self._current_latlon, remote.lat, remote.lon)
        return Place(
            id=f"remote_{remote.lat}_{remote.lon}",
            # No local graph node for a remote hit - main_window._open_routes
            # detects this prefix and routes via Valhalla instead of the
            # local Dijkstra, which has no data for it at all.
            node_id=f"REMOTE:{remote.lat}:{remote.lon}",
            name=remote.name,
            address=remote.address,
            icon=remote.icon,
            category=remote.category,
            distance_mi=distance_mi,
        )

    def _render_results(self, query: str):
        # Blank query (just browsing, or a category chip like "gas near
        # me") has no text to narrow the SQL match, so bound it by distance
        # too — otherwise it's fetching and distance-sorting every place in
        # the whole extract just to show the nearest 40 of them.
        max_distance_mi = None if query.strip() else 15.0
        local_results = fetch_places(query, self._category_filter, max_distance_mi=max_distance_mi)[:_MAX_RESULTS]
        # Remote hits already within the local result set (same rough
        # name+distance) would just be noisy duplicates - a remote POI a
        # few blocks from a local one showing up twice.
        local_names = {(p.name, round(p.distance_mi, 1)) for p in local_results}
        remote_results = [p for p in self._remote_rows if (p.name, round(p.distance_mi, 1)) not in local_names]

        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()

        if not local_results and not remote_results:
            empty = QLabel("No places match. Try a different search.")
            empty.setStyleSheet(DIM_TEXT_STYLE)
            empty.setAlignment(Qt.AlignCenter)
            self.results_layout.addWidget(empty)
        else:
            for place in local_results:
                self.results_layout.addWidget(self._build_row(place))
            if remote_results:
                header = QLabel("Farther away")
                header.setStyleSheet(DIM_TEXT_STYLE)
                self.results_layout.addWidget(header)
                for place in remote_results:
                    self.results_layout.addWidget(self._build_row(place))
        self.results_layout.addStretch(1)

    def _build_row(self, place: Place) -> ClickableWidget:
        row = ClickableWidget()
        row.setStyleSheet(RESULT_ROW_STYLE)
        row.setMinimumHeight(76)
        row.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(16)

        icon = QLabel(place.icon)
        icon.setStyleSheet(RESULT_ICON_STYLE)
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel(place.name)
        name.setStyleSheet(RESULT_NAME_STYLE)
        address = QLabel(place.address)
        address.setStyleSheet(DIM_TEXT_STYLE)
        text_col.addWidget(name)
        text_col.addWidget(address)

        distance = QLabel(f"{place.distance_mi:.1f} mi")
        distance.setStyleSheet(DIM_TEXT_STYLE)

        layout.addWidget(icon)
        layout.addLayout(text_col, 1)
        layout.addWidget(distance)

        row.clicked.connect(lambda p=place: self.detail_overlay.open_for(p))
        return row
