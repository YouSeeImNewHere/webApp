from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from .screens.idle_screen import IdleScreen
from .screens.nav_screen import NavScreen
from .screens.routes_screen import RoutesScreen
from .screens.search_screen import SearchScreen
from .widgets.status_bar import StatusBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quail Maps")

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.status_bar_widget = StatusBar()
        outer.addWidget(self.status_bar_widget)

        # A grid instead of adding self.stack straight into outer — this is
        # what lets RoutesScreen sit as a bottom-sheet overlay layered on
        # top of whichever screen is currently showing, instead of being
        # its own full page in the stack. It used to cover everything for
        # exactly the same reason PlaceDetailScreen did before that got
        # the same treatment: an opaque full-page screen swapped in via
        # setCurrentWidget() replaces what was there instead of overlaying it.
        stage = QWidget()
        outer.addWidget(stage, 1)
        stage_grid = QGridLayout(stage)
        stage_grid.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        stage_grid.addWidget(self.stack, 0, 0)

        self.idle_screen = IdleScreen()
        self.search_screen = SearchScreen()
        self.nav_screen = NavScreen()

        for screen in (self.idle_screen, self.search_screen, self.nav_screen):
            self.stack.addWidget(screen)

        self.routes_screen = RoutesScreen()
        self.routes_screen.hide()
        stage_grid.addWidget(self.routes_screen, 0, 0)
        self.routes_screen.raise_()

        self.idle_screen.search_requested.connect(self._open_search)
        self.idle_screen.destination_selected.connect(self._open_routes)

        self.search_screen.back_requested.connect(self._show_idle)
        # place_selected now fires once "Drive" is picked from the
        # PlaceDetailScreen bottom-sheet overlay owned by SearchScreen
        # itself (see search_screen.py) — tapping a result opens that
        # overlay first instead of jumping straight to routing.
        self.search_screen.place_selected.connect(self._open_routes)

        self.routes_screen.back_requested.connect(self.routes_screen.hide)
        self.routes_screen.start_drive_requested.connect(self._start_navigation)

        self.nav_screen.end_requested.connect(self._show_idle)

        self._show_idle()

    def _show_idle(self):
        self.nav_screen.stop()
        self.routes_screen.hide()
        self.stack.setCurrentWidget(self.idle_screen)

    def _open_search(self, category):
        self.search_screen.open_for(category)
        self.stack.setCurrentWidget(self.search_screen)

    def _open_routes(self, place):
        self.routes_screen.open_for(place)

    def _start_navigation(self, place, route):
        self.routes_screen.hide()
        self.nav_screen.start(place, route)
        self.stack.setCurrentWidget(self.nav_screen)
