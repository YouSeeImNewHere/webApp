from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..system import media_control

_NOW_PLAYING_POLL_MS = 2000


class DashboardScreen(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {theme.BG};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(20)

        header = QHBoxLayout()
        back_btn = QPushButton("‹")
        back_btn.setProperty("role", "iconButton")
        back_btn.setFixedSize(48, 48)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back_requested.emit)
        title = QLabel("Dashboard")
        title.setProperty("role", "routesDestination")
        header.addWidget(back_btn)
        header.addSpacing(12)
        header.addWidget(title)
        header.addStretch(1)
        outer.addLayout(header)

        outer.addWidget(self._build_now_playing_card())
        outer.addWidget(self._build_slider_card(
            "Brightness", media_control.brightness_available(), self._on_brightness_changed,
        ))
        outer.addWidget(self._build_slider_card(
            "Volume", media_control.volume_available(), self._on_volume_changed,
        ))
        outer.addStretch(1)

        self._now_playing_timer = QTimer(self)
        self._now_playing_timer.timeout.connect(self._refresh_now_playing)

    # ---- now playing ----

    def _build_now_playing_card(self) -> QWidget:
        card = QWidget()
        card.setProperty("role", "dashboardCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        self.now_playing_title = QLabel("Nothing playing")
        self.now_playing_title.setProperty("role", "nowPlayingTitle")
        self.now_playing_artist = QLabel("")
        self.now_playing_artist.setProperty("role", "nowPlayingArtist")
        layout.addWidget(self.now_playing_title)
        layout.addWidget(self.now_playing_artist)

        controls = QHBoxLayout()
        controls.addStretch(1)
        prev_btn = QPushButton("⏮")
        prev_btn.setProperty("role", "iconButton")
        prev_btn.setFixedSize(52, 52)
        prev_btn.setCursor(Qt.PointingHandCursor)
        prev_btn.clicked.connect(lambda: media_control.previous_track())

        self.play_pause_btn = QPushButton("⏯")
        self.play_pause_btn.setProperty("role", "iconButton")
        self.play_pause_btn.setFixedSize(52, 52)
        self.play_pause_btn.setCursor(Qt.PointingHandCursor)
        self.play_pause_btn.clicked.connect(self._on_play_pause)

        next_btn = QPushButton("⏭")
        next_btn.setProperty("role", "iconButton")
        next_btn.setFixedSize(52, 52)
        next_btn.setCursor(Qt.PointingHandCursor)
        next_btn.clicked.connect(lambda: media_control.next_track())

        controls.addWidget(prev_btn)
        controls.addWidget(self.play_pause_btn)
        controls.addWidget(next_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        if not media_control.now_playing_available():
            # playerctl isn't installed — the card still renders (rather
            # than vanishing, which would look like a bug) but makes clear
            # why it's permanently blank instead of just looking broken.
            self.now_playing_title.setText("Media control unavailable")
            self.now_playing_artist.setText("playerctl not found on this system")
            for btn in (prev_btn, self.play_pause_btn, next_btn):
                btn.setEnabled(False)

        return card

    def _on_play_pause(self):
        media_control.playpause()
        # No local optimistic state — the next poll tick (within
        # _NOW_PLAYING_POLL_MS) picks up whatever actually happened,
        # avoiding a UI that claims "paused" when the underlying player
        # command silently failed (no player running, etc).
        QTimer.singleShot(300, self._refresh_now_playing)

    def _refresh_now_playing(self):
        info = media_control.get_now_playing()
        if info is None:
            self.now_playing_title.setText("Nothing playing")
            self.now_playing_artist.setText("")
            return
        self.now_playing_title.setText(info["title"])
        subtitle = " · ".join(p for p in (info["artist"], info["album"]) if p)
        self.now_playing_artist.setText(subtitle)

    # ---- sliders ----

    def _build_slider_card(self, label_text: str, available: bool, on_change) -> QWidget:
        card = QWidget()
        card.setProperty("role", "dashboardCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setProperty("role", "dashboardLabel")
        value_label = QLabel("--" if not available else "50%")
        value_label.setProperty("role", "dimLabel")
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(value_label)
        layout.addLayout(row)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(50)
        slider.setEnabled(available)
        slider.setCursor(Qt.PointingHandCursor)
        slider.valueChanged.connect(lambda v: value_label.setText(f"{v}%"))
        # sliderReleased, not valueChanged, for the actual system call —
        # ddcutil in particular is slow (real DDC/CI bus round-trips, often
        # 100-500ms per call), so firing it on every intermediate value
        # while dragging would make the slider itself feel laggy.
        slider.sliderReleased.connect(lambda: on_change(slider.value()))

        layout.addWidget(slider)

        if label_text == "Brightness":
            self.brightness_slider = slider
            self.brightness_value_label = value_label
        else:
            self.volume_slider = slider
            self.volume_value_label = value_label

        return card

    def _on_brightness_changed(self, value: int):
        media_control.set_brightness(value)

    def _on_volume_changed(self, value: int):
        media_control.set_volume(value)

    # ---- lifecycle ----

    def showEvent(self, event):
        super().showEvent(event)
        current_brightness = media_control.get_brightness()
        if current_brightness is not None:
            self.brightness_slider.blockSignals(True)
            self.brightness_slider.setValue(current_brightness)
            self.brightness_value_label.setText(f"{current_brightness}%")
            self.brightness_slider.blockSignals(False)

        current_volume = media_control.get_volume()
        if current_volume is not None:
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(current_volume)
            self.volume_value_label.setText(f"{current_volume}%")
            self.volume_slider.blockSignals(False)

        self._refresh_now_playing()
        self._now_playing_timer.start(_NOW_PLAYING_POLL_MS)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._now_playing_timer.stop()
