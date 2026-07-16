from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from quail_maps_car.main_window import MainWindow as MapsMainWindow

from .dashboard_screen import DashboardScreen
from .music_screen import MusicScreen
from .placeholder_screen import PlaceholderScreen

# (label, emoji) — placeholder glyphs standing in for real icon art until
# there's a proper Quail icon set to drop in.
_APPS = [
    ("home", "🏠", "Home"),
    ("maps", "🗺️", "Maps"),
    ("music", "🎵", "Music"),
    ("car", "🚗", "Car"),
]


class ShellWindow(QMainWindow):
    """The CarPlay-style Quail shell: a left icon panel that switches a
    content stack between the dashboard and each app. quail_maps_car stays
    untouched as its own package — this just re-parents its content widget
    into the shell's stack instead of showing MapsMainWindow standalone."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quail")

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_side_panel())

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)

        self._screens: dict[str, QWidget] = {}
        self._dashboard = DashboardScreen()
        self._add_screen("home", self._dashboard)

        # MapsMainWindow is a QMainWindow purely so quail_maps_car can also
        # run standalone (see its own main.py) — here we only want its
        # actual content, so we lift centralWidget() out and drop the
        # now-empty QMainWindow shell entirely. Qt reparents the widget
        # automatically when it's added to a new layout.
        self._maps_window = MapsMainWindow()
        self._add_screen("maps", self._maps_window.centralWidget())

        self._music_screen = MusicScreen()
        self._add_screen("music", self._music_screen)
        self._add_screen("car", PlaceholderScreen("Quail Car"))

        # Dashboard's now-playing card mirrors Music's playback state —
        # wired here in the shell since both screens are otherwise unaware
        # of each other.
        self._music_screen.track_changed.connect(self._dashboard.now_playing_card.set_track)
        self._music_screen.playing_changed.connect(self._dashboard.now_playing_card.set_playing)
        self._music_screen.position_changed.connect(self._dashboard.now_playing_card.set_position)
        self._dashboard.now_playing_card.previous_requested.connect(self._music_screen.play_previous)
        self._dashboard.now_playing_card.next_requested.connect(self._music_screen.play_next)
        self._dashboard.now_playing_card.seek_requested.connect(self._music_screen.seek)
        self._dashboard.now_playing_card.play_pause_requested.connect(self._music_screen.toggle_play_pause)
        self._dashboard.now_playing_card.shuffle_all_requested.connect(self._music_screen.shuffle_all)

        # Tapping either dashboard card opens its full app — same
        # navigation path as tapping the side panel, so the icon there
        # reflects it too rather than staying stuck on "Home".
        self._dashboard.maps_requested.connect(lambda: self.navigate_to("maps"))
        self._dashboard.music_requested.connect(lambda: self.navigate_to("music"))

        self.navigate_to("home")

    def _add_screen(self, key: str, widget: QWidget):
        self._screens[key] = widget
        self.stack.addWidget(widget)

    def _show_screen(self, key: str):
        self.stack.setCurrentWidget(self._screens[key])

    def navigate_to(self, key: str):
        self._show_screen(key)
        button = self._nav_buttons.get(key)
        if button is not None:
            button.setChecked(True)

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidePanel")
        panel.setFixedWidth(96)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 14, 6, 14)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}

        for key, glyph, label in _APPS:
            button = QPushButton(f"{glyph}\n{label}")
            button.setObjectName("appIconButton")
            button.setCheckable(True)
            button.setFixedHeight(76)
            button.clicked.connect(lambda _checked, k=key: self._show_screen(k))
            self._button_group.addButton(button)
            self._nav_buttons[key] = button
            layout.addWidget(button)

        first_button = self._button_group.buttons()[0]
        first_button.setChecked(True)

        layout.addStretch(1)

        # There's no window chrome in kiosk/fullscreen mode and no physical
        # keyboard to Alt+F4 with — this is the only way to get out of the
        # app once it's running full-screen on the car's touchscreen.
        quit_button = QPushButton("✕")
        quit_button.setObjectName("quitButton")
        quit_button.setFixedHeight(56)
        quit_button.clicked.connect(QApplication.instance().quit)
        layout.addWidget(quit_button)

        return panel
