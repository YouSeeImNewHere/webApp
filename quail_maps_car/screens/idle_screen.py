from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..geo.roadnet import GRAPH
from ..geo.search_db import DISCOVER_CATEGORIES, fetch_places, get_place
from ..theme import CHIP_STYLE
from ..widgets.map_canvas import MapCanvas

SHORTCUTS = [
    ("home", "⌂", "Home"),
    ("work", "\U0001f4bc", "Work"),
    ("recent", "↻", "Recent"),
    ("saved", "★", "Saved"),
]


class IdleScreen(QWidget):
    search_requested = Signal(object)  # category key (str) or None
    destination_selected = Signal(object)  # Place

    def __init__(self, parent=None):
        super().__init__(parent)
        self._framed_once = False

        base = QGridLayout(self)
        base.setContentsMargins(0, 0, 0, 0)

        self.map_bg = MapCanvas()
        self._places = fetch_places()
        self.map_bg.set_places(self._places)
        start = GRAPH.nodes["START"]
        self.map_bg.set_user_position(start.east, start.north)
        base.addWidget(self.map_bg, 0, 0)
        QTimer.singleShot(0, self._frame_initial_view)

        content = QWidget()
        base.addWidget(content, 0, 0)
        content.raise_()

        outer = QVBoxLayout(content)
        outer.setContentsMargins(20, 16, 20, 20)
        outer.setSpacing(14)

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
        outer.addLayout(zoom_row)

        outer.addStretch(1)

        self.where_to_btn = QPushButton("⌕   Where to?")
        self.where_to_btn.setObjectName("whereToButton")
        self.where_to_btn.setMinimumHeight(72)
        self.where_to_btn.setCursor(Qt.PointingHandCursor)
        self.where_to_btn.clicked.connect(lambda: self.search_requested.emit(None))
        outer.addWidget(self.where_to_btn)

        shortcut_grid = QGridLayout()
        shortcut_grid.setSpacing(12)
        for i, (key, icon, label) in enumerate(SHORTCUTS):
            btn = QPushButton(f"{icon}\n{label}")
            btn.setProperty("role", "shortcutTile")
            btn.setMinimumHeight(66)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, k=key: self._on_shortcut(k))
            shortcut_grid.addWidget(btn, 0, i)
        outer.addLayout(shortcut_grid)

        discover_scroll = QScrollArea()
        discover_scroll.setWidgetResizable(True)
        discover_scroll.setFixedHeight(60)
        discover_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        discover_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        discover_scroll.setFrameShape(QScrollArea.NoFrame)
        discover_scroll.setStyleSheet("background: transparent; border: none;")
        discover_scroll.viewport().setStyleSheet("background: transparent;")

        discover_inner = QWidget()
        discover_inner.setStyleSheet("background: transparent;")
        discover_row = QHBoxLayout(discover_inner)
        discover_row.setContentsMargins(0, 0, 0, 0)
        discover_row.setSpacing(10)
        for key, icon, label in DISCOVER_CATEGORIES:
            chip = QPushButton(f"{icon}  {label} nearby")
            chip.setStyleSheet(CHIP_STYLE)
            chip.setMinimumHeight(52)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _checked=False, k=key: self.search_requested.emit(k))
            discover_row.addWidget(chip)
        discover_row.addStretch(1)
        discover_scroll.setWidget(discover_inner)
        outer.addWidget(discover_scroll)

    def _on_shortcut(self, key: str):
        if key in ("home", "work"):
            place = get_place(key)
            if place:
                self.destination_selected.emit(place)
        else:
            self.search_requested.emit(None)

    def _frame_initial_view(self):
        if self._framed_once:
            return
        self._framed_once = True
        start = GRAPH.nodes["START"]
        points = [(start.east, start.north)] + [
            (GRAPH.nodes[p.node_id].east, GRAPH.nodes[p.node_id].north) for p in self._places
        ]
        self.map_bg.frame_points(points, margins=(80, 20, 260, 20))
