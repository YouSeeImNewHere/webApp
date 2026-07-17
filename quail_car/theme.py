from __future__ import annotations

# Single source of truth for colors lives in quail_maps_car.theme — the
# shell reuses them directly so the dashboard and Maps never drift apart
# visually even though they're separate widgets now.
from quail_maps_car.theme import (
    ACCENT,
    BAD_RED,
    BG,
    BORDER,
    GOOD_GREEN,
    SURFACE,
    SURFACE_RAISED,
    TEXT,
    TEXT_DIM,
    WARN_YELLOW,
)

SHELL_STYLESHEET = f"""
QMainWindow {{
    background-color: {BG};
}}

QWidget {{
    color: {TEXT};
    font-family: "Helvetica Neue", Arial, sans-serif;
}}

#sidePanel {{
    background-color: {SURFACE};
    border-right: 1px solid {BORDER};
}}

QPushButton#appIconButton {{
    background-color: transparent;
    border-radius: 18px;
    font-size: 16px;
    font-weight: 700;
    color: {TEXT_DIM};
    padding: 10px 4px;
}}
QPushButton#appIconButton:checked {{
    background-color: {SURFACE_RAISED};
    color: {TEXT};
}}

QPushButton#quitButton {{
    background-color: transparent;
    border: 1px solid {BORDER};
    border-radius: 12px;
    font-size: 18px;
    font-weight: 700;
    color: {BAD_RED};
}}
QPushButton#quitButton:pressed {{
    background-color: {BAD_RED};
    color: white;
}}

QPushButton#settingsToggleButton {{
    background-color: transparent;
    border: 1px solid {BORDER};
    border-radius: 12px;
    font-size: 22px;
    font-weight: 700;
    color: {TEXT_DIM};
}}
QPushButton#settingsToggleButton:pressed {{
    background-color: {SURFACE_RAISED};
    color: {TEXT};
}}

#settingsDrawer {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}

QLabel#dashboardClock {{
    font-size: 84px;
    font-weight: 800;
    color: {TEXT};
}}
QLabel#dashboardDate {{
    font-size: 22px;
    font-weight: 600;
    color: {TEXT_DIM};
}}

#dashboardNowPlaying {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
QLabel#dashboardNowPlayingCover {{
    background-color: {SURFACE};
    border-radius: 10px;
    font-size: 28px;
    color: {TEXT_DIM};
}}
QLabel#dashboardNowPlayingTitle {{
    font-size: 17px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#dashboardNowPlayingArtist {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT_DIM};
}}
QPushButton#dashboardNowPlayingButton {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 24px;
    font-size: 18px;
    color: {TEXT};
}}
QPushButton#dashboardNowPlayingButton:pressed {{
    background-color: {ACCENT};
}}

QLabel#dashboardShuffleIcon {{
    font-size: 36px;
}}
QPushButton#dashboardShuffleButton {{
    background-color: {ACCENT};
    border-radius: 12px;
    font-size: 15px;
    font-weight: 700;
    color: white;
    padding: 0 24px;
}}
QPushButton#dashboardShuffleButton:pressed {{
    background-color: {SURFACE_RAISED};
}}

QLabel#dashboardNowPlayingTime {{
    font-size: 12px;
    font-weight: 600;
    color: {TEXT_DIM};
}}
QSlider#dashboardProgressSlider::groove:horizontal {{
    height: 5px;
    background: {SURFACE};
    border-radius: 2px;
}}
QSlider#dashboardProgressSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider#dashboardProgressSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -6px 0;
    background: {TEXT};
    border-radius: 8px;
}}
QSlider#dashboardProgressSlider::handle:horizontal:pressed {{
    background: {ACCENT};
}}

#dashboardRoadCard {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}

#dashboardNextTurn {{
    background-color: {ACCENT};
    border-radius: 16px;
}}
QLabel#dashboardNextTurnManeuver {{
    font-size: 30px;
    color: white;
}}
QLabel#dashboardNextTurnInstruction {{
    font-size: 18px;
    font-weight: 800;
    color: white;
}}
QLabel#dashboardNextTurnDistance {{
    font-size: 14px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.85);
}}
QLabel#dashboardNextTurnEta {{
    font-size: 20px;
    font-weight: 800;
    color: white;
}}
QLabel#dashboardNextTurnEtaCaption {{
    font-size: 11px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.7);
}}

QPushButton#dashboardQuickAction {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 14px;
    font-size: 16px;
    font-weight: 700;
    color: {TEXT};
}}
QPushButton#dashboardQuickAction:pressed {{
    background-color: {ACCENT};
    color: white;
}}

QLabel#dashboardMusicStatus {{
    font-size: 13px;
    font-weight: 700;
    color: {GOOD_GREEN};
}}

#locationRow {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel#locationRowName {{
    font-size: 16px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#locationRowCoords {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT_DIM};
}}
#locationForm {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QScrollArea#locationScrollArea {{
    background-color: transparent;
    border: none;
}}

QLabel#dashboardSliderIcon {{
    font-size: 18px;
    color: {TEXT_DIM};
}}
QSlider#dashboardSlider::groove:vertical {{
    width: 6px;
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 3px;
}}
QSlider#dashboardSlider::sub-page:vertical {{
    background: {SURFACE_RAISED};
    border-radius: 3px;
}}
QSlider#dashboardSlider::add-page:vertical {{
    background: {ACCENT};
    border-radius: 3px;
}}
QSlider#dashboardSlider::handle:vertical {{
    width: 26px;
    height: 26px;
    margin: 0 -10px;
    background: {TEXT};
    border-radius: 13px;
}}
QSlider#dashboardSlider::handle:vertical:pressed {{
    background: {ACCENT};
}}

QLabel#placeholderTitle {{
    font-size: 26px;
    font-weight: 800;
    color: {TEXT};
}}
QLabel#placeholderSubtitle {{
    font-size: 16px;
    font-weight: 600;
    color: {TEXT_DIM};
}}

QLabel#musicNowPlaying {{
    font-size: 22px;
    font-weight: 800;
    color: {TEXT};
}}
QLabel#musicStatus {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT_DIM};
}}
QPushButton#musicControlButton {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 16px;
    font-size: 17px;
    font-weight: 700;
    color: {TEXT};
}}
QPushButton#musicControlButton:pressed {{
    background-color: {ACCENT};
    color: white;
}}
QPushButton#musicControlButton:checked {{
    background-color: {ACCENT};
    color: white;
    border-color: {ACCENT};
}}
QLineEdit {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 15px;
    color: {TEXT};
}}
QListWidget#musicTrackList {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
    font-size: 16px;
    font-weight: 600;
    padding: 6px;
}}
QListWidget#musicTrackList::item {{
    padding: 10px 8px;
    border-radius: 8px;
}}
QListWidget#musicTrackList::item:selected {{
    background-color: {ACCENT};
    color: white;
}}

#trackRow {{
    background-color: transparent;
}}
QLabel#rowCover {{
    background-color: {SURFACE_RAISED};
    border-radius: 10px;
    font-size: 26px;
    color: {TEXT_DIM};
}}
QLabel#rowTitle {{
    font-size: 18px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#rowSubtitle {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT_DIM};
}}

#miniPlayerBar {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QLabel#miniPlayerCover {{
    background-color: {SURFACE};
    border-radius: 8px;
}}
QLabel#miniPlayerTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#miniPlayerArtist {{
    font-size: 12px;
    font-weight: 600;
    color: {TEXT_DIM};
}}
QPushButton#miniPlayerButton {{
    background-color: transparent;
    border: none;
    font-size: 20px;
    color: {TEXT};
}}

QLabel#nowPlayingCover {{
    background-color: {SURFACE};
    border-radius: 20px;
    font-size: 96px;
    color: {TEXT_DIM};
}}
QLabel#nowPlayingTitle {{
    font-size: 26px;
    font-weight: 800;
    color: {TEXT};
}}
QLabel#nowPlayingArtist {{
    font-size: 17px;
    font-weight: 600;
    color: {TEXT_DIM};
}}
QPushButton#nowPlayingFeedbackButton {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 28px;
    font-size: 22px;
}}
QPushButton#nowPlayingFeedbackButton:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
QPushButton#nowPlayingTransportButton {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 32px;
    font-size: 22px;
    color: {TEXT};
}}
QPushButton#nowPlayingTransportButton:pressed {{
    background-color: {ACCENT};
}}

#virtualKeyboard {{
    background-color: {SURFACE};
    border-top: 1px solid {BORDER};
}}
QPushButton#virtualKeyboardKey {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 8px;
    font-size: 20px;
    color: {TEXT};
}}
QPushButton#virtualKeyboardKey:pressed {{
    background-color: {ACCENT};
}}
"""
