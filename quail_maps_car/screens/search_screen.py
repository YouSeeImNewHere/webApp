from __future__ import annotations

from PySide6.QtCore import Qt, Signal
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

from ..geo.search_db import Place, fetch_places
from ..theme import DIM_TEXT_STYLE, RESULT_ICON_STYLE, RESULT_NAME_STYLE, RESULT_ROW_STYLE
from ..widgets.clickable import ClickableWidget
from ..widgets.opaque_screen import OpaqueScreen
from .place_detail_screen import PlaceDetailScreen

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
        self._refresh_results()
        self.input.setFocus()

    def _on_drive_requested(self, place: Place):
        self.detail_overlay.hide()
        self.place_selected.emit(place)

    def _refresh_results(self):
        query = self.input.text()
        # Blank query (just browsing, or a category chip like "gas near
        # me") has no text to narrow the SQL match, so bound it by distance
        # too — otherwise it's fetching and distance-sorting every place in
        # the whole extract just to show the nearest 40 of them.
        max_distance_mi = None if query.strip() else 15.0
        results = fetch_places(query, self._category_filter, max_distance_mi=max_distance_mi)[:_MAX_RESULTS]

        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()

        if not results:
            empty = QLabel("No offline places match. Try a different search.")
            empty.setStyleSheet(DIM_TEXT_STYLE)
            empty.setAlignment(Qt.AlignCenter)
            self.results_layout.addWidget(empty)
        else:
            for place in results:
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
