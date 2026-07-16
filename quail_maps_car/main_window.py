from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from .screens.idle_screen import IdleScreen
from .screens.nav_screen import NavScreen
from .screens.place_detail_screen import PlaceDetailScreen
from .screens.routes_screen import RoutesScreen
from .screens.search_screen import SearchScreen
from .widgets.status_bar import StatusBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quail Maps")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.status_bar_widget = StatusBar()
        layout.addWidget(self.status_bar_widget)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.idle_screen = IdleScreen()
        self.search_screen = SearchScreen()
        self.place_detail_screen = PlaceDetailScreen()
        self.routes_screen = RoutesScreen()
        self.nav_screen = NavScreen()

        for screen in (
            self.idle_screen,
            self.search_screen,
            self.place_detail_screen,
            self.routes_screen,
            self.nav_screen,
        ):
            self.stack.addWidget(screen)

        self.idle_screen.search_requested.connect(self._open_search)
        # Shortcuts (Home/Work) stay a fast path straight to routing — the
        # detail screen is for picking an arbitrary destination out of
        # search results, where seeing what you're actually navigating to
        # first is worth the extra tap.
        self.idle_screen.destination_selected.connect(self._open_routes)

        self.search_screen.back_requested.connect(self._show_idle)
        self.search_screen.place_selected.connect(self._open_place_detail)

        self.place_detail_screen.back_requested.connect(
            lambda: self.stack.setCurrentWidget(self.search_screen)
        )
        self.place_detail_screen.drive_requested.connect(self._open_routes)

        # Not routed back to place_detail_screen: the Home/Work shortcuts
        # (idle_screen.destination_selected) skip the detail screen
        # entirely and go straight here, so it isn't always populated for
        # wherever routes_screen was actually opened from.
        self.routes_screen.back_requested.connect(lambda: self.stack.setCurrentWidget(self.search_screen))
        self.routes_screen.start_drive_requested.connect(self._start_navigation)

        self.nav_screen.end_requested.connect(self._show_idle)

        self._show_idle()

    def _show_idle(self):
        self.nav_screen.stop()
        self.stack.setCurrentWidget(self.idle_screen)

    def _open_search(self, category):
        self.search_screen.open_for(category)
        self.stack.setCurrentWidget(self.search_screen)

    def _open_place_detail(self, place):
        self.place_detail_screen.open_for(place)
        self.stack.setCurrentWidget(self.place_detail_screen)

    def _open_routes(self, place):
        self.routes_screen.open_for(place)
        self.stack.setCurrentWidget(self.routes_screen)

    def _start_navigation(self, place, route):
        self.nav_screen.start(place, route)
        self.stack.setCurrentWidget(self.nav_screen)
