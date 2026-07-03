from __future__ import annotations

from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from ..theme import BG


class OpaqueScreen(QWidget):
    """A full-screen page that paints its own solid background directly.

    Qt breaks style sheet cascading to a widget's descendants once that
    widget has its own setStyleSheet() call, so painting the background
    color here avoids blocking the app-level stylesheet from reaching this
    screen's buttons/labels.
    """

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(BG))
        super().paintEvent(event)
