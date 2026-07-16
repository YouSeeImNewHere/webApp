from __future__ import annotations

import subprocess

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

# VESA MCCS VCP feature codes.
VCP_BRIGHTNESS = "10"
VCP_VOLUME = "62"


def _run(args: list[str]) -> str | None:
    try:
        result = subprocess.run(["ddcutil", *args], capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _read_vcp(feature: str) -> int | None:
    # --brief output looks like: "VCP 10 C 50 100" (feature, type, current, max)
    output = _run(["getvcp", feature, "--brief"])
    if not output:
        return None
    parts = output.split()
    try:
        return int(parts[3])
    except (IndexError, ValueError):
        return None


class DdcController(QObject):
    """Talks to the car display over DDC/CI via the ddcutil CLI. Every call
    is a blocking I2C round-trip (roughly 0.2-2s), so reads and writes both
    run on Qt's global thread pool — never shell out to ddcutil from the
    main/UI thread."""

    levels_read = Signal(int, int)  # brightness, volume; -1 means unavailable

    def refresh_async(self):
        QThreadPool.globalInstance().start(_ReadTask(self))

    def set_brightness_async(self, value: int):
        QThreadPool.globalInstance().start(_WriteTask(VCP_BRIGHTNESS, value))

    def set_volume_async(self, value: int):
        QThreadPool.globalInstance().start(_WriteTask(VCP_VOLUME, value))


class _ReadTask(QRunnable):
    def __init__(self, controller: DdcController):
        super().__init__()
        self._controller = controller

    def run(self):
        brightness = _read_vcp(VCP_BRIGHTNESS)
        volume = _read_vcp(VCP_VOLUME)
        # Emitted from a worker thread — Qt auto-queues delivery to slots
        # owned by the (main-thread) controller, so this is safe.
        self._controller.levels_read.emit(
            brightness if brightness is not None else -1,
            volume if volume is not None else -1,
        )


class _WriteTask(QRunnable):
    def __init__(self, feature: str, value: int):
        super().__init__()
        self._feature = feature
        self._value = value

    def run(self):
        _run(["setvcp", self._feature, str(self._value)])
