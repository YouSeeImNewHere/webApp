from __future__ import annotations

BG = "#05070b"
SURFACE = "#11151d"
SURFACE_RAISED = "#171c26"
BORDER = "rgba(255,255,255,0.10)"
TEXT = "#f4f6fa"
TEXT_DIM = "#8a93a3"
ACCENT = "#2b6cff"
WARN_YELLOW = "#ffcc33"
GOOD_GREEN = "#34c759"
BAD_RED = "#ff453a"

# Self-contained style for widgets that sit inside a QScrollArea: QScrollArea
# paints its own native panel background that only a *local* style sheet can
# override, but a local style sheet on an ancestor blocks the app-level
# style sheet from reaching its descendants — so these widgets carry their
# full look locally instead of relying on the global stylesheet's cascade.
CHIP_STYLE = f"""
QPushButton {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 22px;
    color: {TEXT};
    font-size: 15px;
    font-weight: 600;
    padding: 0 18px;
}}
"""

# A flat (selector-less) local style sheet on a container leaks its
# border/background into descendants that don't set their own — so every
# plain-text style below explicitly resets both to avoid inheriting a
# container's border (e.g. a selected route card's blue outline).
_RESET = "border: none; background: transparent;"

DIM_TEXT_STYLE = f"color: {TEXT_DIM}; font-size: 14px; font-weight: 600; {_RESET}"

RESULT_ROW_STYLE = f"background: transparent; border-bottom: 1px solid {BORDER};"
RESULT_ICON_STYLE = f"background-color: {SURFACE_RAISED}; border-radius: 12px; font-size: 19px;"
RESULT_NAME_STYLE = f"color: {TEXT}; font-size: 17px; font-weight: 700; {_RESET}"

ROUTE_CARD_STYLE = f"background-color: {SURFACE}; border: 2px solid {BORDER}; border-radius: 16px;"
ROUTE_CARD_SELECTED_STYLE = (
    f"background-color: rgba(43,108,255,0.14); border: 2px solid {ACCENT}; border-radius: 16px;"
)
ROUTE_RANK_STYLE = f"background-color: rgba(255,255,255,0.10); color: {TEXT}; border-radius: 15px; font-size: 13px; font-weight: 700;"
ROUTE_RANK_SELECTED_STYLE = f"background-color: {ACCENT}; color: white; border-radius: 15px; font-size: 13px; font-weight: 700;"
ROUTE_DURATION_STYLE = f"color: {TEXT}; font-size: 19px; font-weight: 800; {_RESET}"
ROUTE_ARRIVAL_TIME_STYLE = f"color: {TEXT}; font-size: 15px; font-weight: 700; {_RESET}"

STYLESHEET = f"""
QMainWindow {{
    background-color: {BG};
}}

QWidget {{
    color: {TEXT};
    font-family: "Helvetica Neue", Arial, sans-serif;
}}

#statusBar {{
    background-color: rgba(5,7,11,0.92);
    border-bottom: 1px solid {BORDER};
}}

QLabel#offlineDot {{
    background-color: {GOOD_GREEN};
    border-radius: 5px;
}}

QLabel#clockLabel {{
    font-size: 17px;
    font-weight: 700;
}}

*[role="dimLabel"] {{
    color: {TEXT_DIM};
    font-size: 14px;
    font-weight: 600;
}}

QPushButton#whereToButton {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 20px;
    padding: 0 24px;
    font-size: 22px;
    font-weight: 700;
    color: {TEXT_DIM};
    text-align: left;
}}

*[role="shortcutTile"] {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 16px;
    font-size: 15px;
    font-weight: 700;
    color: {TEXT_DIM};
}}

QLineEdit#searchInput {{
    background-color: {SURFACE};
    border: 2px solid transparent;
    border-radius: 16px;
    padding: 0 18px;
    font-size: 20px;
}}
QLineEdit#searchInput:focus {{
    border: 2px solid {WARN_YELLOW};
}}

*[role="iconButton"] {{
    background-color: {SURFACE};
    border-radius: 16px;
    font-size: 20px;
}}

*[role="routesDestination"] {{
    font-size: 19px;
    font-weight: 700;
}}

QPushButton#startNavButton {{
    background-color: {ACCENT};
    border-radius: 18px;
    font-size: 20px;
    font-weight: 800;
    color: white;
}}
QPushButton#startNavButton:disabled {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_DIM};
}}

#navBanner, #navBottomBar {{
    background-color: rgba(17,21,29,0.94);
    border-radius: 22px;
}}

QLabel#navManeuverIcon {{
    background-color: {ACCENT};
    border-radius: 32px;
    font-size: 28px;
    font-weight: 800;
    color: white;
}}
*[role="navInstruction"] {{
    font-size: 26px;
    font-weight: 800;
}}
*[role="navDistance"] {{
    font-size: 19px;
    font-weight: 700;
    color: {WARN_YELLOW};
}}

QPushButton#arrivedButton {{
    background-color: {GOOD_GREEN};
    border-radius: 18px;
    font-size: 19px;
    font-weight: 800;
    color: #06210f;
}}

*[role="navEta"] {{
    font-size: 28px;
    font-weight: 800;
}}

QPushButton#navEndButton {{
    background-color: {BAD_RED};
    border-radius: 28px;
    font-size: 16px;
    font-weight: 800;
    color: white;
    padding: 0 28px;
}}

*[role="dashboardCard"] {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 20px;
}}

*[role="dashboardLabel"] {{
    font-size: 16px;
    font-weight: 700;
}}

QSlider::groove:horizontal {{
    height: 8px;
    background: {SURFACE_RAISED};
    border-radius: 4px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 4px;
}}
QSlider::handle:horizontal {{
    background: white;
    width: 28px;
    height: 28px;
    margin: -10px 0;
    border-radius: 14px;
}}

*[role="nowPlayingTitle"] {{
    font-size: 20px;
    font-weight: 800;
}}
*[role="nowPlayingArtist"] {{
    font-size: 15px;
    font-weight: 600;
    color: {TEXT_DIM};
}}
"""
