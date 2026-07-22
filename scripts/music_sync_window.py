#!/usr/bin/env python3
"""A small floating progress window for the MP3 player sync — launched by
music_sync_watch.sh as the very first thing it does once the drive is
detected, so it's already open by the time anything else happens.

Doesn't talk to the sync scripts directly (they're separate processes,
run sequentially by the watch script) — instead it tails
~/Library/Logs/quail_music_sync.log from wherever it was when this window
opened, and parses the same plain-text lines those scripts already print.
That keeps this purely additive: music_sync_mp3_player.py,
music_feedback_sync.py, and music_genre_sync.py don't need to know this
window exists, or change their own output at all.

Stays open until the user dismisses it with one of the two buttons — it
does NOT auto-close, even once the sync finishes, so the final summary is
never missed. "OK" just closes the window (e.g. if you want to make more
changes on the drive before pulling it); "OK and Eject" also ejects every
volume passed on the command line, so it's safe to physically unplug
right after clicking.

Usage: music_sync_window.py [VOLUME_NAME ...]
(defaults to "SSD MP3" and "Y2" if none are given, matching what
music_sync_watch.sh normally passes)
"""
from __future__ import annotations

import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

LOG_PATH = Path.home() / "Library" / "Logs" / "quail_music_sync.log"
POLL_MS = 300
DEFAULT_VOLUME_NAMES = ["SSD MP3", "Y2"]

_LOOKING_UP_RE = re.compile(r"Looking up (\d+) track\(s\) not yet cached")
# Every per-track result line from music_genre_sync.py's sync() loop
# matches exactly one of these — see that file for where each is printed.
_TRACK_RESULT_RE = re.compile(r"\(via (artist|recording)\)|^no genre found for |^no MusicBrainz match for |^failed ")


class SyncWindow:
    def __init__(self, volume_names: list[str]):
        self.volume_names = volume_names
        self.root = tk.Tk()
        self.root.title("Quail Music Sync")
        self.root.geometry("440x340")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        pad = {"padx": 16, "pady": 8}

        self.status_var = tk.StringVar(value="Waiting for sync activity…")
        status_label = ttk.Label(self.root, textvariable=self.status_var, font=("SF Pro", 14, "bold"))
        status_label.pack(anchor="w", **pad)

        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=400)
        self.progress.pack(padx=16, pady=(0, 8))
        self.progress.start(12)
        self._progress_determinate = False

        self.detail_var = tk.StringVar(value="")
        detail_label = ttk.Label(self.root, textvariable=self.detail_var, foreground="#666", wraplength=400)
        detail_label.pack(anchor="w", padx=16)

        # Where the final playlist/genre counts land once "all done" shows
        # up in the log — kept visually distinct from the scrolling raw
        # log below, since that's the part actually meant to be read.
        self.summary_var = tk.StringVar(value="")
        summary_label = ttk.Label(
            self.root, textvariable=self.summary_var, font=("SF Pro", 12), foreground="#1a7a3c", wraplength=400,
        )
        summary_label.pack(anchor="w", padx=16, pady=(4, 0))

        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=16, pady=8)
        self.log_text = tk.Text(log_frame, height=8, wrap="none", font=("Menlo", 10), state="disabled")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        button_row = ttk.Frame(self.root)
        button_row.pack(pady=(0, 12))
        # Plain "OK" is the deliberate no-eject option — for when you want
        # to make more changes on the drive (add a playlist file, etc.)
        # before physically pulling it.
        self.ok_button = ttk.Button(button_row, text="OK", command=self.root.destroy)
        self.ok_button.pack(side="left", padx=6)
        self.eject_button = ttk.Button(button_row, text="OK and Eject", command=self._eject_and_close)
        self.eject_button.pack(side="left", padx=6)

        self._track_count = 0
        self._track_total = 0
        self._playlist_summary = ""

        # Skip any pre-existing content — only new lines written from this
        # point on are this run's activity, not a stale previous run's.
        self._pos = LOG_PATH.stat().st_size if LOG_PATH.exists() else 0

        self.root.after(POLL_MS, self._poll)

    def _poll(self):
        if LOG_PATH.exists():
            with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
            if chunk:
                for line in chunk.splitlines():
                    self._handle_line(line)
        if self.root.winfo_exists():
            self.root.after(POLL_MS, self._poll)

    def _handle_line(self, line: str):
        stripped = line.strip()
        if not stripped:
            return

        if "detected, syncing" in line:
            self.status_var.set("Syncing playlists…")
        elif "JELLYFIN_API_KEY not set" in line or "isn't mounted" in line:
            self.status_var.set("Sync failed")
            self.summary_var.set(stripped)
        elif "sync finished" in line:
            self.status_var.set("Playlist sync complete")
        elif stripped.startswith("Done syncing to"):
            # music_sync_mp3_player.py's own final summary line, e.g.
            # "Done syncing to /Volumes/SSD MP3: Daily Jams: 27 tracks • ..."
            self._playlist_summary = stripped.split(": ", 1)[-1] if ": " in stripped else stripped
        elif "submitting feedback events" in line:
            self.status_var.set("Submitting feedback to ListenBrainz…")
        elif "No feedback events found" in line:
            self.status_var.set("No feedback to submit")
        elif "looking up genres for new tracks" in line:
            self.status_var.set("Looking up genres…")
            self._set_indeterminate()
        elif (m := _LOOKING_UP_RE.search(line)) is not None:
            self._track_total = int(m.group(1))
            self._track_count = 0
            self._set_determinate(self._track_total)
        elif "Every track already has a cached genre" in line:
            self.status_var.set("Genres already up to date")
        elif _TRACK_RESULT_RE.search(stripped) is not None and self._progress_determinate:
            self._track_count += 1
            self.progress["value"] = self._track_count
            self.detail_var.set(f"{self._track_count} / {self._track_total} tracks")
        elif stripped.startswith("Done: "):
            genre_summary = stripped[len("Done: "):]
            self._set_final_summary(genre_summary)
        elif stripped.endswith("all done"):
            self.status_var.set("Sync complete")
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=1, value=1)
            if not self.summary_var.get():
                self._set_final_summary(None)
            self.ok_button.focus_set()

        self._append_log(stripped)

    def _set_final_summary(self, genre_summary: str | None):
        parts = []
        if self._playlist_summary:
            parts.append(self._playlist_summary)
        if genre_summary:
            parts.append(f"Genres — {genre_summary}")
        self.summary_var.set("\n".join(parts) if parts else "Sync complete.")

    def _set_indeterminate(self):
        self._progress_determinate = False
        self.progress.stop()
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)

    def _set_determinate(self, total: int):
        self._progress_determinate = True
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=max(1, total), value=0)

    def _append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        # Cap displayed history — this window is a live glance, not a full
        # log viewer (that's still ~/Library/Logs/quail_music_sync.log).
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 500:
            self.log_text.delete("1.0", f"{line_count - 500}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _eject_and_close(self):
        # Best-effort per volume — one already being unmounted (or never
        # having been mounted in the first place, e.g. Y2 not plugged in
        # today) shouldn't stop the others from ejecting or block closing
        # the window.
        for name in self.volume_names:
            volume_path = f"/Volumes/{name}"
            if not Path(volume_path).exists():
                continue
            try:
                subprocess.run(["diskutil", "eject", volume_path], check=False, timeout=15)
            except (OSError, subprocess.SubprocessError):
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    names = sys.argv[1:] or DEFAULT_VOLUME_NAMES
    SyncWindow(names).run()
