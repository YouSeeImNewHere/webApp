from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DashboardScreen(QWidget):
    """Quail's CarPlay-style home screen. Deliberately minimal for now — a
    clock is the only thing every "neat dashboard" needs on day one. Easy to
    grow later (currently-playing track, next turn, etc.) once Music/Maps
    have state worth surfacing here."""

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        self.clock_label = QLabel()
        self.clock_label.setObjectName("dashboardClock")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.clock_label)

        self.date_label = QLabel()
        self.date_label.setObjectName("dashboardDate")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.date_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def _tick(self):
        now = datetime.now()
        self.clock_label.setText(now.strftime("%-I:%M"))
        self.date_label.setText(now.strftime("%A, %B %-d"))
