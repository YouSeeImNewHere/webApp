from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGridLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from .carlink import PAIRED_PHONE_MAC, BluetoothCarLink
from .geo.latlon import latlon_to_local, local_to_latlon, nearest_routable_node
from .geo.search_db import Place
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
        self.nav_screen.position_updated.connect(self._on_position_updated)

        # Set just before start_selected_route() is called from a remote
        # (phone-triggered) start, read once by _start_navigation() right
        # after — see _on_remote_start_drive()'s docstring for why this
        # exists instead of threading overrides through the existing
        # start_drive_requested(place, route) signal directly.
        self._pending_remote_overrides: tuple[int, float] | None = None

        # Phone-as-remote-control: while a phone is Bluetooth-connected
        # (see carlink/), a destination picked there is routed and driven
        # using the car's own local extract data, not the phone's — the
        # phone only ever sends coordinates + a name, never a route.
        self.car_link = BluetoothCarLink(PAIRED_PHONE_MAC)
        self.car_link.destination_received.connect(self._on_remote_destination)
        self.car_link.start_drive_requested.connect(self._on_remote_start_drive)
        self.car_link.position_received.connect(self._on_remote_position)
        self.car_link.start()

        self._show_idle()

    def _on_remote_destination(self, lat: float, lon: float, name: str):
        print(f"[carlink] destination_received: lat={lat} lon={lon} name={name!r}", flush=True)
        node = nearest_routable_node(lat, lon)
        if node is None:
            print("[carlink] nearest_routable_node returned None (no extract loaded / bad origin)", flush=True)
            self.car_link.send_error("No routable road data near that location")
            return
        print(f"[carlink] snapped to node {node.id}, opening routes", flush=True)
        place = Place(
            id=f"phone_{node.id}",
            node_id=node.id,
            name=name or "Phone Destination",
            address="",
            icon="\U0001f4f1",
            category="destination",
        )
        self._open_routes(place)

    def _on_remote_start_drive(self, minutes: int, distance_mi: float, _retries_left: int = 10) -> None:
        # The car's own local routing engine (its downloaded extract +
        # Dijkstra) and the phone's server-backed one can legitimately
        # disagree on distance/ETA for the same destination — different
        # road data, different algorithm. Rather than show two different
        # numbers on two screens for the same drive, whatever the phone
        # already computed (sent here) wins for display; the car still
        # drives its own actual path/steps, just labels progress using the
        # phone's numbers when it sent real ones (-1/-1.0 means it didn't).
        if minutes >= 0 and distance_mi >= 0:
            self._pending_remote_overrides = (minutes, distance_mi)
        # RoutesScreen's routes come back from an async worker (SQL-heavy
        # route computation, see routes_screen.py) — a phone tap on "start"
        # can easily arrive before that finishes. Retrying briefly instead
        # of dropping the request outright is what makes tapping start
        # right after picking a destination on the phone actually work.
        started = self.routes_screen.start_selected_route()
        if not started and _retries_left > 0:
            QTimer.singleShot(300, lambda: self._on_remote_start_drive(minutes, distance_mi, _retries_left - 1))
        elif not started:
            self._pending_remote_overrides = None
            self.car_link.send_error("No route ready to start")

    def _on_remote_position(self, lat: float, lon: float) -> None:
        local = latlon_to_local(lat, lon)
        if local is None:
            return
        east, north = local
        self.nav_screen.update_from_real_position(east, north)

    def _on_position_updated(self, east: float, north: float, heading: float, eta_min: int, remaining_mi: float):
        # send_position() is itself a no-op with no connected phone
        # (BluetoothCarLink._send short-circuits when _client_sock is
        # None) — no need to gate this call on connection state here too.
        latlon = local_to_latlon(east, north)
        if latlon is None:
            return
        lat, lon = latlon
        self.car_link.send_position(lat, lon, heading, eta_min, remaining_mi)

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
        overrides, self._pending_remote_overrides = self._pending_remote_overrides, None
        if overrides is not None:
            self.nav_screen.set_display_overrides(*overrides)
        self.stack.setCurrentWidget(self.nav_screen)
        self.car_link.send_route_confirmed(route.minutes, route.distance_mi)
