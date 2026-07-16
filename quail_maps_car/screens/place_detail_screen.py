from __future__ import annotations

import subprocess
import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..geo.search_db import Place
from ..theme import ACCENT, BORDER, DIM_TEXT_STYLE, SURFACE, SURFACE_RAISED, TEXT, TEXT_DIM

# Mirrors QuailAndroid's PlaceDetailContent (TileMapScreen.kt): icon, name,
# category, a Drive action, Call/Website (only shown when the data has
# them), Hours + Distance stat blocks, and the address. Call/Website open
# best-effort via the OS (xdg-open / a browser) rather than failing loudly
# if nothing's configured to handle them — this is a car computer, not a
# phone, so there's no guarantee either actually does anything useful, but
# tapping them shouldn't be able to crash the screen either.

_PILL_STYLE = f"""
QPushButton {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 14px;
    color: {TEXT};
    font-size: 14px;
    font-weight: 700;
    padding: 10px 18px;
}}
"""

_DRIVE_PILL_STYLE = f"""
QPushButton {{
    background-color: {ACCENT};
    border: none;
    border-radius: 14px;
    color: white;
    font-size: 14px;
    font-weight: 800;
    padding: 10px 22px;
}}
"""


class PlaceDetailScreen(QWidget):
    """A bottom-sheet overlay, not a full page — this sits on top of
    whatever's behind it (dimmed, not hidden) sized to its own content, the
    same way Android's version slides up over the map instead of replacing
    it with a blank screen. Meant to be layered into a parent's grid/stack
    at the same cell as the content behind it and shown/hidden on demand,
    not pushed as its own page in the app's main screen stack."""

    back_requested = Signal()
    drive_requested = Signal(object)  # Place

    def __init__(self, parent=None):
        super().__init__(parent)
        self._place: Place | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # Empty space above the card is left transparent (just the dim
        # scrim painted below) — tapping there doesn't do anything yet,
        # but visually it reads as "still on the results screen, dimmed,"
        # not "this is now the whole app."
        outer.addStretch(1)

        card = QWidget()
        card.setObjectName("placeDetailCard")
        card.setStyleSheet(
            f"""
            #placeDetailCard {{
                background-color: {SURFACE};
                border-top-left-radius: 24px;
                border-top-right-radius: 24px;
                border: 1px solid {BORDER};
            }}
            """
        )
        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(18)

        header_row = QHBoxLayout()
        header_row.setSpacing(14)

        self.icon_label = QLabel("")
        self.icon_label.setFixedSize(56, 56)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet(
            f"background-color: {SURFACE_RAISED}; border-radius: 28px; font-size: 24px;"
        )
        header_row.addWidget(self.icon_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.name_label = QLabel("")
        self.name_label.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: 800;")
        self.name_label.setWordWrap(True)
        self.category_label = QLabel("")
        self.category_label.setStyleSheet(DIM_TEXT_STYLE)
        title_col.addWidget(self.name_label)
        title_col.addWidget(self.category_label)
        header_row.addLayout(title_col, 1)

        close_btn = QPushButton("✕")
        close_btn.setProperty("role", "iconButton")
        close_btn.setFixedSize(48, 48)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.back_requested.emit)
        header_row.addWidget(close_btn)

        root.addLayout(header_row)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)

        self.drive_btn = QPushButton("🚗  Drive")
        self.drive_btn.setStyleSheet(_DRIVE_PILL_STYLE)
        self.drive_btn.setCursor(Qt.PointingHandCursor)
        self.drive_btn.clicked.connect(self._on_drive)
        actions_row.addWidget(self.drive_btn)

        self.call_btn = QPushButton("📞  Call")
        self.call_btn.setStyleSheet(_PILL_STYLE)
        self.call_btn.setCursor(Qt.PointingHandCursor)
        self.call_btn.clicked.connect(self._on_call)
        actions_row.addWidget(self.call_btn)

        self.website_btn = QPushButton("🌐  Website")
        self.website_btn.setStyleSheet(_PILL_STYLE)
        self.website_btn.setCursor(Qt.PointingHandCursor)
        self.website_btn.clicked.connect(self._on_website)
        actions_row.addWidget(self.website_btn)

        actions_row.addStretch(1)
        root.addLayout(actions_row)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(32)
        self.hours_value = self._build_stat(stats_row, "Hours")
        self.distance_value = self._build_stat(stats_row, "Distance")
        stats_row.addStretch(1)
        root.addLayout(stats_row)

        self.address_label = QLabel("")
        self.address_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 14px;")
        self.address_label.setWordWrap(True)
        root.addWidget(self.address_label)

    def paintEvent(self, event):
        # Dims whatever's behind this overlay rather than covering it with
        # an opaque background — the card itself (painted via its own
        # stylesheet above) is the only fully-opaque part.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))
        super().paintEvent(event)

    def _build_stat(self, row: QHBoxLayout, label_text: str) -> QLabel:
        col = QVBoxLayout()
        col.setSpacing(2)
        label = QLabel(label_text)
        label.setStyleSheet(DIM_TEXT_STYLE)
        value = QLabel("")
        value.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: 700;")
        col.addWidget(label)
        col.addWidget(value)
        row.addLayout(col)
        return value

    def open_for(self, place: Place):
        self._place = place
        self.icon_label.setText(place.icon or "📍")
        self.name_label.setText(place.name)
        self.category_label.setText(place.category.title() if place.category else "")
        self.hours_value.setText(place.opening_hours or "Not listed")
        self.distance_value.setText(f"{place.distance_mi:.1f} mi")
        self.address_label.setText(place.address)
        self.call_btn.setVisible(bool(place.phone))
        self.website_btn.setVisible(bool(place.website))
        self.show()
        self.raise_()

    def _on_drive(self):
        if self._place is not None:
            self.drive_requested.emit(self._place)

    def _on_call(self):
        if self._place is None or not self._place.phone:
            return
        # Best-effort — there's no cellular modem in a car computer, so
        # this most likely does nothing on most setups, but shouldn't be
        # able to crash the screen if it fails.
        try:
            subprocess.Popen(["xdg-open", f"tel:{self._place.phone}"])
        except OSError:
            pass

    def _on_website(self):
        if self._place is None or not self._place.website:
            return
        try:
            webbrowser.open(self._place.website)
        except Exception:
            pass
