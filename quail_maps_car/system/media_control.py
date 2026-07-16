from __future__ import annotations

import shutil
import subprocess

# VCP feature code 0x10 ("Brightness") in the DDC/CI spec ddcutil speaks —
# universal across monitors that support DDC/CI at all, not a
# vendor-specific code.
_BRIGHTNESS_VCP_CODE = "10"

_DDCUTIL = shutil.which("ddcutil")
_PACTL = shutil.which("pactl")
_PLAYERCTL = shutil.which("playerctl")

# Every function here is a best-effort wrapper around an external CLI tool
# that may or may not be installed on a given car build — None/False
# returns mean "unavailable," not "zero"/"off", so DashboardScreen can
# distinguish "no monitor supports DDC/CI here" from "brightness is
# actually at 0".


def brightness_available() -> bool:
    return _DDCUTIL is not None


def get_brightness() -> int | None:
    if _DDCUTIL is None:
        return None
    try:
        result = subprocess.run(
            [_DDCUTIL, "getvcp", _BRIGHTNESS_VCP_CODE],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    # Typical ddcutil output: "VCP 10 C 62 100" (current, max) — pull the
    # "current" field rather than assuming a fixed column count, since the
    # exact format has varied across ddcutil versions.
    for token in result.stdout.split():
        if token.isdigit():
            return int(token)
    return None


def set_brightness(percent: int) -> bool:
    if _DDCUTIL is None:
        return False
    percent = max(0, min(100, percent))
    try:
        result = subprocess.run(
            [_DDCUTIL, "setvcp", _BRIGHTNESS_VCP_CODE, str(percent)],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0


def volume_available() -> bool:
    return _PACTL is not None


def get_volume() -> int | None:
    if _PACTL is None:
        return None
    try:
        result = subprocess.run(
            [_PACTL, "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    # "Volume: front-left: 45875 /  70% / ..." — the first "NN%" token is
    # what pactl itself considers the current level.
    for token in result.stdout.split():
        if token.endswith("%"):
            try:
                return int(token.rstrip("%"))
            except ValueError:
                continue
    return None


def set_volume(percent: int) -> bool:
    if _PACTL is None:
        return False
    percent = max(0, min(100, percent))
    try:
        result = subprocess.run(
            [_PACTL, "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0


def now_playing_available() -> bool:
    return _PLAYERCTL is not None


def get_now_playing() -> dict | None:
    """Reads whatever's currently playing via MPRIS (playerctl) — works
    with any MPRIS-compliant player (browser tabs, Spotify, VLC, etc.)
    without this app needing to know which one is actually running."""
    if _PLAYERCTL is None:
        return None
    try:
        result = subprocess.run(
            [_PLAYERCTL, "metadata", "--format", "{{status}}\t{{artist}}\t{{title}}\t{{album}}"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    parts = result.stdout.strip("\n").split("\t")
    while len(parts) < 4:
        parts.append("")
    status, artist, title, album = parts[:4]
    if not title:
        return None
    return {"status": status, "artist": artist, "title": title, "album": album}


def playpause() -> bool:
    return _playerctl_cmd("play-pause")


def next_track() -> bool:
    return _playerctl_cmd("next")


def previous_track() -> bool:
    return _playerctl_cmd("previous")


def _playerctl_cmd(action: str) -> bool:
    if _PLAYERCTL is None:
        return False
    try:
        result = subprocess.run([_PLAYERCTL, action], capture_output=True, text=True, timeout=5)
    except (subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0
