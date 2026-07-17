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

from quail_maps_car.geo.roadnet import GRAPH
from quail_maps_car.widgets.map_canvas import MapCanvas

from . import album_art
from .music_library import Track

_COVER_SIZE = 88
_DDC_DEBOUNCE_MS = 150
# Tight enough that this card reads as "what road am I on," not a mini
# version of the full Maps app — matches NavScreen's own street-level
# framing (quail_maps_car/screens/nav_screen.py NAV_VIEW_RADIUS_M).
_ROAD_CARD_RADIUS_M = 45.0


def _format_ms(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


class _JumpToClickSlider(QSlider):
    """A QSlider where clicking (or dragging) anywhere in the groove jumps
    the handle straight to that position, rather than Qt's default of
    treating a groove click as a page-step and only jumping if you land
    exactly on the handle. On a touchscreen, "tap where you want the level"
    is the whole point — nobody's grabbing a 26px handle precisely with a
    finger."""

    def _value_at(self, pos) -> int:
        span = self.maximum() - self.minimum()
        if self.orientation() == Qt.Orientation.Vertical:
            # Vertical sliders run bottom (min) to top (max) — invert Y.
            fraction = 1.0 - (pos.y() / max(1, self.height()))
        else:
            fraction = pos.x() / max(1, self.width())
        fraction = max(0.0, min(1.0, fraction))
        return self.minimum() + round(fraction * span)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self._value_at(event.position()))
            # QAbstractSlider's own press/move/release handling — which
            # normally emits sliderPressed/sliderReleased — never runs
            # since this whole handler replaces it for left clicks.
            # _NowPlayingCard's seek bar depends on those two signals to
            # know when to stop treating player position updates as
            # authoritative, so they're emitted explicitly here.
            self.sliderPressed.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.setValue(self._value_at(event.position()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _NowPlayingCard(QWidget):
    """Now-playing block for the dashboard: cover art, title/artist, a
    seekable progress bar with elapsed/total time, and full transport
    (prev/play-pause/next) — mirrors what Music's own now-playing screen
    shows, just permanently visible here instead of a tap away. Always
    visible — before anything's played, shows a "Shuffle All Songs" button
    in place of the track content instead of disappearing entirely."""

    play_pause_requested = Signal()
    previous_requested = Signal()
    next_requested = Signal()
    seek_requested = Signal(int)  # position_ms
    open_requested = Signal()
    shuffle_all_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("dashboardNowPlaying")
        # QSS background/border on a plain QWidget is otherwise silently
        # ignored — Qt only paints a widget's own stylesheet box when this
        # is set, which is why the border on this card (and _RoadCard's)
        # wasn't actually rendering before despite being in theme.py.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self._duration_ms = 0
        # While the user is dragging/tapping the seek bar, incoming
        # positionChanged updates from the player would otherwise fight the
        # gesture and snap the handle back to the actual playback position
        # mid-drag.
        self._seeking = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        self._idle_content = self._build_idle_content()
        outer.addWidget(self._idle_content)

        self._track_content = QWidget()
        track_layout = QVBoxLayout(self._track_content)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(12)
        outer.addWidget(self._track_content)
        self._track_content.setVisible(False)

        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        self.cover_label = QLabel()
        self.cover_label.setObjectName("dashboardNowPlayingCover")
        self.cover_label.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(self.cover_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        text_col.addStretch(1)
        self.title_label = QLabel("")
        self.title_label.setObjectName("dashboardNowPlayingTitle")
        self.artist_label = QLabel("")
        self.artist_label.setObjectName("dashboardNowPlayingArtist")
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.artist_label)
        text_col.addStretch(1)
        top_row.addLayout(text_col, 1)
        track_layout.addLayout(top_row)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        self.elapsed_label = QLabel("0:00")
        self.elapsed_label.setObjectName("dashboardNowPlayingTime")
        self.progress_slider = _JumpToClickSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setObjectName("dashboardProgressSlider")
        self.progress_slider.setRange(0, 0)
        self.progress_slider.sliderPressed.connect(self._on_seek_pressed)
        self.progress_slider.sliderReleased.connect(self._on_seek_released)
        self.duration_label = QLabel("0:00")
        self.duration_label.setObjectName("dashboardNowPlayingTime")
        progress_row.addWidget(self.elapsed_label)
        progress_row.addWidget(self.progress_slider, 1)
        progress_row.addWidget(self.duration_label)
        track_layout.addLayout(progress_row)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(18)
        controls_row.addStretch(1)
        self.prev_button = QPushButton("⏮")
        self.play_button = QPushButton("▶")
        self.next_button = QPushButton("⏭")
        for button in (self.prev_button, self.play_button, self.next_button):
            button.setObjectName("dashboardNowPlayingButton")
            button.setFixedSize(48, 48)
            button.setCursor(Qt.PointingHandCursor)
        self.play_button.setFixedSize(56, 56)
        self.prev_button.clicked.connect(self.previous_requested)
        self.play_button.clicked.connect(self.play_pause_requested)
        self.next_button.clicked.connect(self.next_requested)
        controls_row.addWidget(self.prev_button)
        controls_row.addWidget(self.play_button)
        controls_row.addWidget(self.next_button)
        controls_row.addStretch(1)
        track_layout.addLayout(controls_row)

    def _build_idle_content(self) -> QWidget:
        idle = QWidget()
        layout = QVBoxLayout(idle)
        layout.setContentsMargins(0, 20, 0, 20)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("\U0001f500")
        icon.setObjectName("dashboardShuffleIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        shuffle_button = QPushButton("Shuffle All Songs")
        shuffle_button.setObjectName("dashboardShuffleButton")
        shuffle_button.setFixedHeight(48)
        shuffle_button.setCursor(Qt.PointingHandCursor)
        # A real QPushButton click, not the card's own mousePressEvent —
        # consumes the press itself, same as the transport buttons do, so
        # this doesn't also fire open_requested and jump to the Music
        # screen on top of starting shuffle playback.
        shuffle_button.clicked.connect(self.shuffle_all_requested)
        layout.addWidget(shuffle_button)

        return idle

    def _on_seek_pressed(self):
        self._seeking = True

    def _on_seek_released(self):
        self._seeking = False
        self.seek_requested.emit(self.progress_slider.value())

    def set_track(self, track: Track | None):
        if track is None:
            self._idle_content.setVisible(True)
            self._track_content.setVisible(False)
            return
        self._idle_content.setVisible(False)
        self._track_content.setVisible(True)
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

    def set_position(self, position_ms: int, duration_ms: int):
        self._duration_ms = duration_ms
        self.duration_label.setText(_format_ms(duration_ms))
        if self.progress_slider.maximum() != duration_ms:
            self.progress_slider.setRange(0, duration_ms)
        if self._seeking:
            # Don't fight an in-progress drag/tap with the player's own
            # position updates — see the flag's docstring above.
            return
        self.progress_slider.blockSignals(True)
        self.progress_slider.setValue(position_ms)
        self.progress_slider.blockSignals(False)
        self.elapsed_label.setText(_format_ms(position_ms))

    def mousePressEvent(self, event):
        # Only ever fires for clicks that land on this widget's own
        # background/labels — the transport buttons and progress slider
        # are separate child widgets that consume their own presses first,
        # so tapping them plays/pauses/seeks as normal instead of also
        # navigating away to the Music screen.
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit()
        super().mousePressEvent(event)


class _SliderRow(QWidget):
    """One labeled 0-100 vertical slider used for the dashboard's
    brightness/volume rail — icon below a tall jump-to-tap slider, CarPlay
    dock style."""

    value_committed = Signal(int)

    def __init__(self, glyph: str, initial: int = 50):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.slider = _JumpToClickSlider(Qt.Orientation.Vertical)
        self.slider.setObjectName("dashboardSlider")
        self.slider.setRange(0, 100)
        self.slider.setValue(initial)
        # Qt's vertical QSlider default (invertedAppearance=False) already
        # puts maximum at the top / minimum at the bottom — matching a
        # physical fader ("up = more") and matching _value_at()'s own
        # top=max assumption above. A previous pass set this to True
        # believing the default needed flipping, which actually did the
        # opposite: it made the rendered handle position invert relative to
        # what tapping the rail set the value to (tap top -> value jumps to
        # max, but the handle then visually snapped to the bottom). Left
        # unset here to use Qt's correct default.
        self.slider.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.slider, 1, Qt.AlignmentFlag.AlignHCenter)

        icon = QLabel(glyph)
        icon.setObjectName("dashboardSliderIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

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


class _NextTurnCard(QWidget):
    """Mirrors quail_maps_car's nav banner (maneuver glyph, next
    instruction, distance-to-turn, ETA) on the dashboard, so you don't have
    to leave whatever app you're in just to see "what's my next turn."
    Hidden whenever there's no active route — most of the time, this card
    simply isn't there."""

    open_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("dashboardNextTurn")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        self.maneuver_label = QLabel("↑")
        self.maneuver_label.setObjectName("dashboardNextTurnManeuver")
        self.maneuver_label.setFixedSize(52, 52)
        self.maneuver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.maneuver_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.instruction_label = QLabel("")
        self.instruction_label.setObjectName("dashboardNextTurnInstruction")
        self.instruction_label.setWordWrap(True)
        self.distance_label = QLabel("")
        self.distance_label.setObjectName("dashboardNextTurnDistance")
        text_col.addWidget(self.instruction_label)
        text_col.addWidget(self.distance_label)
        layout.addLayout(text_col, 1)

        eta_col = QVBoxLayout()
        eta_col.setSpacing(2)
        self.eta_label = QLabel("")
        self.eta_label.setObjectName("dashboardNextTurnEta")
        self.eta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        eta_caption = QLabel("ETA")
        eta_caption.setObjectName("dashboardNextTurnEtaCaption")
        eta_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        eta_col.addWidget(self.eta_label)
        eta_col.addWidget(eta_caption)
        layout.addLayout(eta_col)

        self.hide()

    def set_instruction(self, maneuver: str, instruction: str, distance_text: str, eta_text: str):
        self.maneuver_label.setText(maneuver)
        self.instruction_label.setText(instruction)
        self.distance_label.setText(distance_text)
        self.eta_label.setText(eta_text)
        self.show()

    def clear(self):
        self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit()
        super().mousePressEvent(event)


class _RoadCard(QWidget):
    """Tightly-zoomed, read-only slice of the loaded road graph centered on
    the car's current position — "what road am I on" at a glance, not a
    small version of the interactive Maps app. Reuses quail_maps_car's own
    MapCanvas/GRAPH rather than a second renderer, so it's always drawing
    from the same offline extract data Maps itself uses."""

    open_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("dashboardRoadCard")
        # See _NowPlayingCard's __init__ for why this is needed for the
        # border/background to actually paint.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        # A few px of margin, not 0 — at 0 the map's own opaque paintEvent
        # (a full-rect fill, see quail_maps_car's MapCanvas) draws right up
        # to the widget edge and covers this card's border entirely, so
        # the "border" in theme.py was rendering underneath the map with
        # nothing visible.
        layout.setContentsMargins(3, 3, 3, 3)

        self.map_bg = MapCanvas()
        self.map_bg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.map_bg)

        start = GRAPH.nodes.get("START")
        if start is not None:
            self.map_bg.set_user_position(start.east, start.north)
            self.map_bg.center_on_with_radius(start.east, start.north, _ROAD_CARD_RADIUS_M)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit()
        super().mousePressEvent(event)


class DashboardScreen(QWidget):
    """Quail's CarPlay-style home screen: a clock plus a road-position card
    and now-playing block side by side — each opens its full app
    (Maps / Music) when tapped. Brightness/volume live in the shell's
    global settings drawer (see settings_drawer.py), reachable from any
    screen — no longer duplicated here."""

    maps_requested = Signal()
    music_requested = Signal()
    navigate_home_requested = Signal()
    play_last_requested = Signal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(18)

        self.next_turn_card = _NextTurnCard()
        self.next_turn_card.open_requested.connect(self.maps_requested)
        layout.addWidget(self.next_turn_card)

        layout.addStretch(1)

        self.clock_label = QLabel()
        self.clock_label.setObjectName("dashboardClock")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.clock_label)

        self.date_label = QLabel()
        self.date_label.setObjectName("dashboardDate")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.date_label)

        layout.addStretch(1)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(18)

        self.road_card = _RoadCard()
        self.road_card.setFixedHeight(220)
        self.road_card.open_requested.connect(self.maps_requested)
        cards_row.addWidget(self.road_card, 1)

        self.now_playing_card = _NowPlayingCard()
        self.now_playing_card.open_requested.connect(self.music_requested)
        cards_row.addWidget(self.now_playing_card, 1)

        layout.addLayout(cards_row)

        # Tells you the library actually finished scanning and is ready to
        # play, rather than wondering whether tapping "Play Last Playlist"
        # right after a fresh boot will do anything yet.
        self.music_status_label = QLabel("")
        self.music_status_label.setObjectName("dashboardMusicStatus")
        self.music_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.music_status_label)

        quick_actions_row = QHBoxLayout()
        quick_actions_row.setSpacing(18)

        navigate_home_button = QPushButton("\U0001f3e0 Navigate Home")
        navigate_home_button.setObjectName("dashboardQuickAction")
        navigate_home_button.setFixedHeight(56)
        navigate_home_button.setCursor(Qt.PointingHandCursor)
        navigate_home_button.clicked.connect(self.navigate_home_requested)
        quick_actions_row.addWidget(navigate_home_button, 1)

        play_last_button = QPushButton("▶ Play Last Playlist")
        play_last_button.setObjectName("dashboardQuickAction")
        play_last_button.setFixedHeight(56)
        play_last_button.setCursor(Qt.PointingHandCursor)
        play_last_button.clicked.connect(self.play_last_requested)
        quick_actions_row.addWidget(play_last_button, 1)

        layout.addLayout(quick_actions_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def _tick(self):
        now = datetime.now()
        self.clock_label.setText(now.strftime("%-I:%M"))
        self.date_label.setText(now.strftime("%A, %B %-d"))

    def set_music_ready(self, is_ready: bool):
        self.music_status_label.setText("\U0001f3b5 Music Ready" if is_ready else "")
