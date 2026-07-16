from __future__ import annotations

import os
import sys

# Must be set before QApplication is constructed. This switches from the
# earlier "onboard" external-app approach (which stole window-manager focus
# on every tap, so keystrokes never actually reached the field) to Qt's own
# virtual keyboard, which renders as an overlay inside this app's own window
# instead of a separate top-level window — no focus stealing, real key
# events land directly in the focused widget, and it docks properly.
os.environ.setdefault("QT_IM_MODULE", "qtvirtualkeyboard")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .shell_window import ShellWindow
from .theme import SHELL_STYLESHEET

# quail_maps_car ships its own stylesheet for widgets it defines by
# objectName/role — apply both so Maps still looks right once it's a screen
# inside the shell instead of its own top-level window.
from quail_maps_car.theme import STYLESHEET as MAPS_STYLESHEET


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(MAPS_STYLESHEET + SHELL_STYLESHEET)

    window = ShellWindow()
    window.resize(1280, 800)

    if "--windowed" in sys.argv:
        # The 800x800 (well, 1280x800) touchscreen panel has zero room to
        # spare — a window manager's title bar on top of a 1280x800 client
        # area pushes the bottom edge off a screen that's only 800px tall.
        # --windowed is for quick dev testing, so strip decorations to match
        # what showFullScreen() below already gets for free.
        window.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        window.show()
    else:
        window.showFullScreen()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
