from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLineEdit, QPushButton, QWidget

# QWERTY rows, lowercase — deliberately no shift/caps layer. This is a
# search box for artist/song names, not a general-purpose text editor;
# search is already case-insensitive (see music_screen.py's _refresh_list
# lowercasing both the query and the fields it compares against), so
# there's no real cost to keeping this simpler.
_ROWS = [
    "1234567890",
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
]

_KEY_SIZE = 52
_KEY_SPACING = 4


class VirtualKeyboard(QWidget):
    """A fully self-contained on-screen keyboard — no external app, no Qt
    input-method plugin. Both of those were tried here before this
    (see main.py's history: an external "onboard" app that stole window
    focus on every tap, then QT_IM_MODULE=qtvirtualkeyboard which turned
    out to hang the whole app on this hardware) and both failed in ways
    that made typing impossible. This is just ordinary QPushButtons
    inserting text into whichever QLineEdit last attached — nothing here
    depends on anything outside this app's own event loop.

    Hidden by default; call attach(line_edit) to show it and start
    directing keypresses there, detach() to hide it again.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("virtualKeyboard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._target: QLineEdit | None = None

        layout = QGridLayout(self)
        layout.setSpacing(_KEY_SPACING)
        layout.setContentsMargins(8, 8, 8, 8)

        for row_index, row in enumerate(_ROWS):
            # Each row after the first is inset half a key width, the same
            # staggered look a real QWERTY keyboard has — purely cosmetic,
            # doesn't affect hit-testing since each button still owns its
            # own grid cell.
            col_offset = row_index
            for col_index, char in enumerate(row):
                button = self._make_key(char, on_click=lambda _c=False, ch=char: self._insert(ch))
                layout.addWidget(button, row_index, col_index * 2 + col_offset, 1, 2)

        bottom_row = len(_ROWS)
        space_button = self._make_key("space", on_click=lambda: self._insert(" "))
        space_button.setMinimumWidth(_KEY_SIZE * 5)
        layout.addWidget(space_button, bottom_row, 2, 1, 10)

        backspace_button = self._make_key("⌫", on_click=lambda: self._backspace())
        layout.addWidget(backspace_button, bottom_row, 0, 1, 2)

        done_button = self._make_key("Done", on_click=lambda: self.detach())
        layout.addWidget(done_button, bottom_row, 14, 1, 4)

        self.hide()

    def _make_key(self, label: str, on_click) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName("virtualKeyboardKey")
        button.setFixedHeight(_KEY_SIZE)
        button.setCursor(Qt.PointingHandCursor)
        # The one line that makes an on-screen keyboard actually usable:
        # without this, clicking a key first moves focus to the button
        # itself, firing the target QLineEdit's focusOutEvent — which
        # (before this widget existed) was exactly what hid the input
        # method on the very first keypress. NoFocus means the click never
        # touches focus at all, so the QLineEdit stays focused throughout.
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(on_click)
        return button

    def attach(self, line_edit: QLineEdit) -> None:
        self._target = line_edit
        self.show()
        self.raise_()

    def detach(self) -> None:
        self._target = None
        self.hide()

    def _insert(self, text: str) -> None:
        if self._target is not None:
            self._target.insert(text)

    def _backspace(self) -> None:
        if self._target is not None:
            self._target.backspace()
