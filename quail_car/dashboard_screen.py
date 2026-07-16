from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import album_art
from .ddc_control import DdcController
from .music_library import Track

_COVER_SIZE = 72
_DDC_DEBOUNCE_MS = 150


class _NowPlayingCard(QWidget):
    """Compact now-playing summary for the dashboard — mirrors Music's
    mini-player bar but stays visible without switching to the Music
    screen. Hidden entirely until something has actually played."""

    play_pause_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("dashboardNowPlaying")
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(14)

        self.cover_label = QLabel()
        self.cover_label.setObjectName("dashboardNowPlayingCover")
        self.cover_label.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.cover_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title_label = QLabel("")
        self.title_label.setObjectName("dashboardNowPlayingTitle")
        self.artist_label = QLabel("")
        self.artist_label.setObjectName("dashboardNowPlayingArtist")
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.artist_label)
        layout.addLayout(text_col, 1)

        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("dashboardNowPlayingButton")
        self.play_button.setFixedSize(48, 48)
        self.play_button.setCursor(Qt.PointingHandCursor)
        self.play_button.clicked.connect(self.play_pause_requested)
        layout.addWidget(self.play_button)

    def set_track(self, track: Track | None):
        if track is None:
            self.setVisible(False)
            return
        self.setVisible(True)
        self.title_label.setText(track.title)
        self.artist_label.setText(track.artist)
        pixmap = album_art.get_cover_pixmap(track.path)
        if pixmap is not None:
            self.cover_label.setPixmap(
                pixmap.scaled(
                    _COVER_SIZE,
                    _COVER_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.cover_label.setPixmap(QPixmap())
            self.cover_label.setText("♪")

    def set_playing(self, is_playing: bool):
        self.play_button.setText("⏸" if is_playing else "▶")


class _SliderRow(QWidget):
    """One labeled 0-100 slider used for the dashboard's brightness/volume
    controls."""

    value_committed = Signal(int)

    def __init__(self, glyph: str, initial: int = 50):
        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        icon = QLabel(glyph)
        icon.setObjectName("dashboardSliderIcon")
        icon.setFixedWidth(28)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("dashboardSlider")
        self.slider.setRange(0, 100)
        self.slider.setValue(initial)
        self.slider.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.slider, 1)

        # ddcutil is a blocking I2C round-trip (0.2-2s) — committing on
        # every valueChanged tick during a drag would queue up dozens of
        # subprocess calls. Debounce to one write per pause in dragging.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DDC_DEBOUNCE_MS)
        self._debounce.timeout.connect(lambda: self.value_committed.emit(self.slider.value()))

    def _on_value_changed(self, _value: int):
        self._debounce.start()

    def set_value_silently(self, value: int):
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)


class DashboardScreen(QWidget):
    """Quail's CarPlay-style home screen: clock, a now-playing summary fed
    by Quail Music, and display brightness/volume sliders driven over
    DDC/CI via ddcutil."""

    def __init__(self):
        super().__init__()

        self._ddc = DdcController()
        self._ddc.levels_read.connect(self._on_levels_read)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(18)

        layout.addStretch(2)

        self.clock_label = QLabel()
        self.clock_label.setObjectName("dashboardClock")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.clock_label)

        self.date_label = QLabel()
        self.date_label.setObjectName("dashboardDate")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.date_label)

        layout.addStretch(1)

        self.now_playing_card = _NowPlayingCard()
        layout.addWidget(self.now_playing_card)

        self.brightness_row = _SliderRow("☀")  # ☀
        self.brightness_row.value_committed.connect(self._ddc.set_brightness_async)
        layout.addWidget(self.brightness_row)

        self.volume_row = _SliderRow("\U0001f50a")  # 🔊
        self.volume_row.value_committed.connect(self._ddc.set_volume_async)
        layout.addWidget(self.volume_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

        self._ddc.refresh_async()

    def _tick(self):
        now = datetime.now()
        self.clock_label.setText(now.strftime("%-I:%M"))
        self.date_label.setText(now.strftime("%A, %B %-d"))

    def _on_levels_read(self, brightness: int, volume: int):
        # -1 means ddcutil isn't available or the display doesn't report
        # that feature (e.g. running --windowed on a dev laptop) — leave
        # the slider at its default rather than snapping it to 0.
        if brightness >= 0:
            self.brightness_row.set_value_silently(brightness)
        if volume >= 0:
            self.volume_row.set_value_silently(volume)
