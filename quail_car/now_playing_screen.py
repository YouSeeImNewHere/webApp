from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import album_art
from .music_library import Track

_COVER_SIZE = 340


class NowPlayingScreen(QWidget):
    """Full-screen Spotify-style now-playing view: big cover art, transport
    controls, and Like/Dislike. Lives inside Quail Music's inner stack —
    swapped in when you tap the mini-player bar, swapped back out via the
    back arrow."""

    back_requested = Signal()
    prev_requested = Signal()
    play_pause_requested = Signal()
    next_requested = Signal()
    like_requested = Signal()
    dislike_requested = Signal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 24)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        back_row = QHBoxLayout()
        self.back_button = QPushButton("⌄  Now Playing")
        self.back_button.setObjectName("musicControlButton")
        self.back_button.setFixedHeight(40)
        self.back_button.clicked.connect(self.back_requested)
        back_row.addWidget(self.back_button)
        back_row.addStretch(1)
        layout.addLayout(back_row)

        layout.addStretch(1)

        self.cover_label = QLabel()
        self.cover_label.setObjectName("nowPlayingCover")
        self.cover_label.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setScaledContents(False)
        layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.title_label = QLabel("No track loaded")
        self.title_label.setObjectName("nowPlayingTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.artist_label = QLabel("")
        self.artist_label.setObjectName("nowPlayingArtist")
        self.artist_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.artist_label)

        feedback_row = QHBoxLayout()
        feedback_row.setSpacing(16)
        self.dislike_button = QPushButton("👎")
        self.like_button = QPushButton("♡")
        for button in (self.dislike_button, self.like_button):
            button.setObjectName("nowPlayingFeedbackButton")
            button.setFixedSize(56, 56)
        self.like_button.setCheckable(True)
        self.dislike_button.clicked.connect(self.dislike_requested)
        self.like_button.clicked.connect(self.like_requested)
        feedback_row.addStretch(1)
        feedback_row.addWidget(self.dislike_button)
        feedback_row.addWidget(self.like_button)
        feedback_row.addStretch(1)
        layout.addLayout(feedback_row)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(20)
        self.prev_button = QPushButton("⏮")
        self.play_button = QPushButton("▶")
        self.next_button = QPushButton("⏭")
        for button in (self.prev_button, self.play_button, self.next_button):
            button.setObjectName("nowPlayingTransportButton")
            button.setFixedSize(64, 64)
        self.play_button.setFixedSize(80, 80)
        self.prev_button.clicked.connect(self.prev_requested)
        self.play_button.clicked.connect(self.play_pause_requested)
        self.next_button.clicked.connect(self.next_requested)
        controls_row.addStretch(1)
        controls_row.addWidget(self.prev_button)
        controls_row.addWidget(self.play_button)
        controls_row.addWidget(self.next_button)
        controls_row.addStretch(1)
        layout.addLayout(controls_row)

        layout.addStretch(2)

    def set_track(self, track: Track | None):
        if track is None:
            self.title_label.setText("No track loaded")
            self.artist_label.setText("")
            self.cover_label.setPixmap(QPixmap())
            return
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

    def set_liked(self, is_liked: bool):
        self.like_button.setChecked(is_liked)
        self.like_button.setText("♥" if is_liked else "♡")
