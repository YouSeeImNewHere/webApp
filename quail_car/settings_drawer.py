from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .dashboard_screen import _SliderRow
from .ddc_control import DdcController

_DRAWER_WIDTH = 120


class SettingsDrawer(QWidget):
    """Brightness/volume sliders, reachable from any screen via the side
    panel's arrow toggle — not just the dashboard. A separate DdcController
    instance from the dashboard's own rail: both talk to the same physical
    display over DDC/CI, so a write from either one lands correctly either
    way, just without live-mirroring the other rail's handle position while
    both happen to be visible at once (a real but minor tradeoff against
    the complexity of sharing one controller across two independently
    creatable widgets)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsDrawer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(_DRAWER_WIDTH)

        self._ddc = DdcController()
        self._ddc.levels_read.connect(self._on_levels_read)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 28, 16, 28)
        layout.setSpacing(16)

        self.brightness_row = _SliderRow("☀")
        self.brightness_row.value_committed.connect(self._ddc.set_brightness_async)
        layout.addWidget(self.brightness_row)

        self.volume_row = _SliderRow("\U0001f50a")
        self.volume_row.value_committed.connect(self._ddc.set_volume_async)
        layout.addWidget(self.volume_row)

        self.hide()

    def _on_levels_read(self, brightness: int, volume: int):
        if brightness >= 0:
            self.brightness_row.set_value_silently(brightness)
        if volume >= 0:
            self.volume_row.set_value_silently(volume)

    def show_drawer(self):
        self._ddc.refresh_async()
        self.show()
        self.raise_()

    def hide_drawer(self):
        self.hide()

    def toggle(self):
        if self.isVisible():
            self.hide_drawer()
        else:
            self.show_drawer()
