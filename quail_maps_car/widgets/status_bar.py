from __future__ import annotations

from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)

        left = QWidget()
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.offline_dot = QLabel()
        self.offline_dot.setObjectName("offlineDot")
        self.offline_dot.setFixedSize(10, 10)

        self.status_label = QLabel("Offline maps ready")
        self.status_label.setProperty("role", "dimLabel")

        left_layout.addWidget(self.offline_dot)
        left_layout.addWidget(self.status_label)

        self.clock_label = QLabel("--:--")
        self.clock_label.setObjectName("clockLabel")
        self.clock_label.setAlignment(Qt.AlignCenter)

        self.gps_label = QLabel("GPS: searching…")
        self.gps_label.setProperty("role", "dimLabel")

        layout.addWidget(left, 0, Qt.AlignLeft)
        layout.addStretch(1)
        layout.addWidget(self.clock_label, 0, Qt.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(self.gps_label, 0, Qt.AlignRight)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(15000)
        self._tick()

    def _tick(self):
        self.clock_label.setText(QTime.currentTime().toString("h:mm AP"))
