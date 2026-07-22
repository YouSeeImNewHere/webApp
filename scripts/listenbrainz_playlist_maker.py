#!/usr/bin/env python3
"""A small GUI for building a ListenBrainz playlist by hand — search
MusicBrainz for specific artists/songs, curate a list, and push it to a
real playlist under your ListenBrainz account.

Why this exists: Explo (the self-hosted service already driving Daily
Jams / Weekly Exploration onto the MP3 player, see music_sync_watch.sh)
only picks new music algorithmically from ListenBrainz's own
recommendations, or by importing a playlist you already built on Spotify/
Apple Music/ListenBrainz. There's no "just type an artist name" interface
anywhere in that pipeline — this fills that gap for the ListenBrainz side
specifically, since Explo already knows how to import a ListenBrainz
playlist once one exists under your account.

This tool still doesn't talk to Explo's API directly (it doesn't have one
for this) — but once a playlist is created here, this window copies its
link to the clipboard and opens Explo's web UI for you, so the only
manual step left is clicking "+ Import" there and pasting.

Run:
    export LISTENBRAINZ_TOKEN=<your token from listenbrainz.org/settings/>
    python3 scripts/listenbrainz_playlist_maker.py

(Or set LISTENBRAINZ_TOKEN in ~/.config/quail_music/env once — same file
music_sync_watch.sh already reads it from — and this picks it up
automatically without needing to export it every time.)

Set EXPLO_URL if your instance isn't at the default homelab address, e.g.:
    export EXPLO_URL=http://100.69.144.70:7288
"""
from __future__ import annotations

import os
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

import requests

MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
EXPLO_URL = os.environ.get("EXPLO_URL", "http://100.69.144.70:7288")
LISTENBRAINZ_API = "https://api.listenbrainz.org/1"
USER_AGENT = "QuailMusic/1.0 ( personal car computer project )"
ENV_FILE = Path.home() / ".config" / "quail_music" / "env"

# MusicBrainz asks unauthenticated clients to stay at ~1 req/sec — search
# runs on a background thread so the UI doesn't freeze while this sleep
# happens.
_SEARCH_DEBOUNCE_SEC = 1.0


def _load_token() -> str:
    token = os.environ.get("LISTENBRAINZ_TOKEN", "")
    if token:
        return token
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if line.startswith("LISTENBRAINZ_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


class PlaylistMaker:
    def __init__(self):
        self.token = _load_token()
        # (mbid, artist, title, album) — the playlist being built, in order.
        self.added_tracks: list[tuple[str, str, str, str]] = []
        self._last_search_time = 0.0

        self.root = tk.Tk()
        self.root.title("ListenBrainz Playlist Maker")
        self.root.geometry("720x560")

        if not self.token:
            messagebox.showwarning(
                "No LISTENBRAINZ_TOKEN found",
                f"Set LISTENBRAINZ_TOKEN in your environment or in {ENV_FILE}\n"
                "before creating a playlist (search still works without it).",
            )

        self._build_ui()

    # ---- layout ----

    def _build_ui(self):
        pad = {"padx": 12, "pady": 8}

        search_frame = ttk.Frame(self.root)
        search_frame.pack(fill="x", **pad)

        ttk.Label(search_frame, text="Artist").grid(row=0, column=0, sticky="w")
        self.artist_entry = ttk.Entry(search_frame, width=28)
        self.artist_entry.grid(row=1, column=0, padx=(0, 8))

        ttk.Label(search_frame, text="Song (optional)").grid(row=0, column=1, sticky="w")
        self.title_entry = ttk.Entry(search_frame, width=28)
        self.title_entry.grid(row=1, column=1, padx=(0, 8))

        search_button = ttk.Button(search_frame, text="Search", command=self._on_search)
        search_button.grid(row=1, column=2)
        self.artist_entry.bind("<Return>", lambda _e: self._on_search())
        self.title_entry.bind("<Return>", lambda _e: self._on_search())

        self.search_status_var = tk.StringVar(value="")
        ttk.Label(search_frame, textvariable=self.search_status_var, foreground="#666").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

        # Results (left) and the playlist being built (right), side by side.
        lists_frame = ttk.Frame(self.root)
        lists_frame.pack(fill="both", expand=True, padx=12)

        results_col = ttk.Frame(lists_frame)
        results_col.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ttk.Label(results_col, text="Search results — double-click to add").pack(anchor="w")
        self.results_list = tk.Listbox(results_col, activestyle="none")
        self.results_list.pack(fill="both", expand=True)
        self.results_list.bind("<Double-Button-1>", self._on_add_result)
        self._results_data: list[tuple[str, str, str, str]] = []

        playlist_col = ttk.Frame(lists_frame)
        playlist_col.pack(side="left", fill="both", expand=True, padx=(6, 0))
        ttk.Label(playlist_col, text="Playlist — double-click to remove").pack(anchor="w")
        self.playlist_list = tk.Listbox(playlist_col, activestyle="none")
        self.playlist_list.pack(fill="both", expand=True)
        self.playlist_list.bind("<Double-Button-1>", self._on_remove_track)

        # Create/append row.
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill="x", padx=12, pady=(0, 12))

        ttk.Label(bottom_frame, text="Playlist name").grid(row=0, column=0, sticky="w")
        self.playlist_name_entry = ttk.Entry(bottom_frame, width=40)
        self.playlist_name_entry.grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.playlist_name_entry.insert(0, "New Playlist")

        self.create_button = ttk.Button(
            bottom_frame, text="Create on ListenBrainz", command=self._on_create_playlist
        )
        self.create_button.grid(row=1, column=1)

        result_row = ttk.Frame(self.root)
        result_row.pack(fill="x", padx=12, pady=(0, 12))
        self.result_var = tk.StringVar(value="")
        result_label = ttk.Label(result_row, textvariable=self.result_var, foreground="#1a7a3c", wraplength=560)
        result_label.pack(side="left", fill="x", expand=True)
        self.copy_link_button = ttk.Button(result_row, text="Copy Link", command=self._on_copy_link, state="disabled")
        self.copy_link_button.pack(side="right")

        self._last_playlist_url = ""

    # ---- search ----

    def _on_search(self):
        artist = self.artist_entry.get().strip()
        title = self.title_entry.get().strip()
        if not artist and not title:
            return
        self.search_status_var.set("Searching…")
        self.results_list.delete(0, "end")
        self._results_data = []
        threading.Thread(target=self._search_worker, args=(artist, title), daemon=True).start()

    def _search_worker(self, artist: str, title: str):
        # Respect MusicBrainz's courtesy rate limit even across repeated
        # searches in one session, not just within a single lookup.
        elapsed = time.monotonic() - self._last_search_time
        if elapsed < _SEARCH_DEBOUNCE_SEC:
            time.sleep(_SEARCH_DEBOUNCE_SEC - elapsed)
        self._last_search_time = time.monotonic()

        query_parts = []
        if artist:
            query_parts.append(f'artist:"{artist}"')
        if title:
            query_parts.append(f'recording:"{title}"')
        query = " AND ".join(query_parts)

        try:
            resp = requests.get(
                f"{MUSICBRAINZ_API}/recording",
                params={"query": query, "fmt": "json", "limit": 25, "inc": "releases"},
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            recordings = resp.json().get("recordings", [])
        except requests.RequestException as exc:
            # Same "as exc" unbinding issue as _create_worker's except
            # block below — capture the message now, not in the lambda.
            error_message = str(exc)
            self.root.after(0, lambda: self.search_status_var.set(f"Search failed: {error_message}"))
            return

        rows = []
        for rec in recordings:
            mbid = rec.get("id", "")
            rec_title = rec.get("title", "")
            artist_credit = rec.get("artist-credit", [])
            rec_artist = artist_credit[0]["name"] if artist_credit else "Unknown Artist"
            releases = rec.get("releases", [])
            album = releases[0].get("title", "") if releases else ""
            if mbid and rec_title:
                rows.append((mbid, rec_artist, rec_title, album))

        self.root.after(0, lambda: self._show_results(rows))

    def _show_results(self, rows: list[tuple[str, str, str, str]]):
        self._results_data = rows
        self.results_list.delete(0, "end")
        for _mbid, artist, title, album in rows:
            label = f"{artist} — {title}" + (f"  ({album})" if album else "")
            self.results_list.insert("end", label)
        self.search_status_var.set(f"{len(rows)} result(s)" if rows else "No results")

    # ---- playlist building ----

    def _on_add_result(self, _event):
        selection = self.results_list.curselection()
        if not selection:
            return
        track = self._results_data[selection[0]]
        if track in self.added_tracks:
            return
        self.added_tracks.append(track)
        _mbid, artist, title, album = track
        self.playlist_list.insert("end", f"{artist} — {title}" + (f"  ({album})" if album else ""))

    def _on_remove_track(self, _event):
        selection = self.playlist_list.curselection()
        if not selection:
            return
        index = selection[0]
        del self.added_tracks[index]
        self.playlist_list.delete(index)

    # ---- ListenBrainz playlist creation ----

    def _on_create_playlist(self):
        if not self.token:
            messagebox.showerror(
                "No token", f"Set LISTENBRAINZ_TOKEN in your environment or in {ENV_FILE} first."
            )
            return
        if not self.added_tracks:
            messagebox.showwarning("Empty playlist", "Add at least one track first.")
            return
        name = self.playlist_name_entry.get().strip() or "New Playlist"
        self.create_button.state(["disabled"])
        self.result_var.set("Creating playlist on ListenBrainz…")
        threading.Thread(target=self._create_worker, args=(name, list(self.added_tracks)), daemon=True).start()

    def _create_worker(self, name: str, tracks: list[tuple[str, str, str, str]]):
        payload = {
            "playlist": {
                "title": name,
                # ListenBrainz's server-side validation requires this
                # exact extension block with a "public" boolean present —
                # without it the API rejects the whole request with a 400
                # and no further detail. "public": True so it's visible
                # for Explo (or anything else under the same account) to
                # pick up without needing extra sharing steps.
                "extension": {
                    "https://musicbrainz.org/doc/jspf#playlist": {
                        "public": True,
                    }
                },
                "track": [
                    {"identifier": f"https://musicbrainz.org/recording/{mbid}"}
                    for mbid, _artist, _title, _album in tracks
                ],
            }
        }
        try:
            resp = requests.post(
                f"{LISTENBRAINZ_API}/playlist/create",
                json=payload,
                headers={"Authorization": f"Token {self.token}"},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            # exc is unbound the instant this except block ends (Python
            # deletes "as" targets on exit) — the lambda below only runs
            # later, once root.after fires, so it needs its own copy
            # captured now rather than reading the name at call time.
            error_message = str(exc)
            self.root.after(0, lambda: self._on_create_failed(error_message))
            return

        playlist_mbid = data.get("playlist_mbid", "")
        self.root.after(0, lambda: self._on_create_done(playlist_mbid))

    def _on_create_failed(self, message: str):
        self.create_button.state(["!disabled"])
        self.result_var.set(f"Failed to create playlist: {message}")

    def _on_create_done(self, playlist_mbid: str):
        self.create_button.state(["!disabled"])
        if not playlist_mbid:
            self.result_var.set("Playlist created, but no playlist ID was returned — check ListenBrainz directly.")
            return

        url = f"https://listenbrainz.org/playlist/{playlist_mbid}"
        self._last_playlist_url = url
        self.copy_link_button.state(["!disabled"])

        # Already on the clipboard by the time Explo's import dialog is
        # actually open — the "Copy Link" button is there as a fallback,
        # not the primary path, since the whole point here is not having
        # to hunt for the link again.
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        webbrowser.open(EXPLO_URL)

        self.result_var.set(
            f"Created and copied to clipboard: {url}\n"
            f"Explo should now be open — click \"+ Import\" and paste."
        )

    def _on_copy_link(self):
        if not self._last_playlist_url:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self._last_playlist_url)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    PlaylistMaker().run()
