"""Records like/dislike/skip events onto the currently-mounted drive, since
the car computer never has internet of its own to submit them anywhere
directly. scripts/music_feedback_sync.py (run on the Mac, same trigger as
the existing music_sync_mp3_player.py launchd watcher) reads this file next
time the drive comes home and submits it to ListenBrainz.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .music_library import Track, active_volume

FEEDBACK_FILENAME = "quail_feedback.jsonl"


def append_event(action: str, track: Track) -> None:
    volume = active_volume()
    if volume is None:
        return  # nothing mounted right now — the event is simply lost, same
        # as any other action taken with no drive plugged in.
    path = volume / FEEDBACK_FILENAME
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "artist": track.artist,
        "title": track.title,
        "album": track.album,
    }
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError:
        pass
