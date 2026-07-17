from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import saved_locations
from .music_screen import TouchLineEdit
from .virtual_keyboard import VirtualKeyboard


class _LocationRow(QWidget):
    navigate_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, name: str, lat: float, lon: float):
        super().__init__()
        self.setObjectName("locationRow")
        # A plain QWidget subclass otherwise silently ignores its QSS
        # background/border — same fix already needed for the dashboard's
        # own cards (see dashboard_screen.py's _NowPlayingCard).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_label = QLabel(name)
        name_label.setObjectName("locationRowName")
        coord_label = QLabel(f"{lat:.5f}, {lon:.5f}")
        coord_label.setObjectName("locationRowCoords")
        text_col.addWidget(name_label)
        text_col.addWidget(coord_label)
        layout.addLayout(text_col, 1)

        navigate_button = QPushButton("Navigate")
        navigate_button.setObjectName("musicControlButton")
        navigate_button.setFixedHeight(44)
        navigate_button.clicked.connect(lambda: self.navigate_requested.emit(name))
        layout.addWidget(navigate_button)

        delete_button = QPushButton("Delete")
        delete_button.setObjectName("musicControlButton")
        delete_button.setFixedHeight(44)
        delete_button.clicked.connect(lambda: self.delete_requested.emit(name))
        layout.addWidget(delete_button)


class SettingsScreen(QWidget):
    """Lets the driver define named locations (Home, Work, ...) for the
    dashboard's "Navigate Home" quick action and one-tap driving in
    general — separate from quail_maps_car's own search, since a manually
    entered lat/lon works even for places that aren't in the currently
    loaded map extract's POI data."""

    navigate_requested = Signal(float, float, str)

    def __init__(self, current_latlon_provider):
        super().__init__()
        # Callable, not a stored value — always asks for whatever the car's
        # most recent real GPS fix from the phone is at the moment "Use
        # Current Position" is actually tapped, not whatever it was when
        # this screen was constructed.
        self._current_latlon_provider = current_latlon_provider

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel("Saved Locations")
        title.setObjectName("placeholderTitle")
        root.addWidget(title)

        subtitle = QLabel("Define Home, Work, or anywhere else for one-tap navigation.")
        subtitle.setObjectName("placeholderSubtitle")
        root.addWidget(subtitle)

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._list_container)
        scroll.setObjectName("locationScrollArea")
        root.addWidget(scroll, 1)

        form = QWidget()
        form.setObjectName("locationForm")
        form.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(16, 16, 16, 16)
        form_layout.setSpacing(10)

        form_layout.addWidget(QLabel("Add a location"))

        fields_row = QHBoxLayout()
        fields_row.setSpacing(10)
        self.name_input = TouchLineEdit()
        self.name_input.setPlaceholderText("Name (e.g. Home)")
        self.lat_input = TouchLineEdit()
        self.lat_input.setPlaceholderText("Latitude")
        self.lon_input = TouchLineEdit()
        self.lon_input.setPlaceholderText("Longitude")
        for field in (self.name_input, self.lat_input, self.lon_input):
            field.setFixedHeight(44)
            field.focused_in.connect(lambda f=field: self.keyboard.attach(f))
            fields_row.addWidget(field)
        form_layout.addLayout(fields_row)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)
        use_current_button = QPushButton("Use Current Position")
        use_current_button.setObjectName("musicControlButton")
        use_current_button.setFixedHeight(44)
        use_current_button.clicked.connect(self._use_current_position)
        buttons_row.addWidget(use_current_button)

        save_button = QPushButton("Save Location")
        save_button.setObjectName("musicControlButton")
        save_button.setFixedHeight(44)
        save_button.clicked.connect(self._save_location)
        buttons_row.addWidget(save_button)
        form_layout.addLayout(buttons_row)

        root.addWidget(form)

        # Same self-contained on-screen keyboard Music uses, and floated
        # the same way (not laid out in `root`) — laying it out directly
        # pushed content off the bottom of the 1280x800 screen the first
        # time this exact mistake was made in music_screen.py.
        self.keyboard = VirtualKeyboard(self)

        self._refresh_list()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        height = self.keyboard.sizeHint().height()
        self.keyboard.setGeometry(0, self.height() - height, self.width(), height)

    def _use_current_position(self):
        latlon = self._current_latlon_provider()
        if latlon is None:
            QMessageBox.warning(
                self, "No Position Available",
                "No GPS fix from the phone yet — connect over Bluetooth and try again.",
            )
            return
        lat, lon = latlon
        self.lat_input.setText(f"{lat:.6f}")
        self.lon_input.setText(f"{lon:.6f}")

    def _save_location(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Enter a name for this location.")
            return
        try:
            lat = float(self.lat_input.text().strip())
            lon = float(self.lon_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Invalid Coordinates", "Latitude and longitude must be numbers.")
            return
        saved_locations.save_location(name, lat, lon)
        self.name_input.clear()
        self.lat_input.clear()
        self.lon_input.clear()
        self.keyboard.detach()
        self._refresh_list()

    def _refresh_list(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        locations = saved_locations.load_locations()
        for name, entry in locations.items():
            row = _LocationRow(name, entry["lat"], entry["lon"])
            row.navigate_requested.connect(self._on_navigate)
            row.delete_requested.connect(self._on_delete)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    def _on_navigate(self, name: str):
        location = saved_locations.get_location(name)
        if location is None:
            return
        lat, lon = location
        self.navigate_requested.emit(lat, lon, name)

    def _on_delete(self, name: str):
        saved_locations.delete_location(name)
        self._refresh_list()
