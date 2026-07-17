from __future__ import annotations

import random

from PySide6.QtCore import QSize, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScroller,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import album_art, feedback_log, music_library
from .music_library import Playlist, Track
from .now_playing_screen import NowPlayingScreen
from .virtual_keyboard import VirtualKeyboard

_BACK_TO_ARTISTS = "‹ Back to Artists"
_BACK_TO_GENRES = "‹ Back to Genres"
_LIKED_PLAYLIST_NAME = "Liked Songs"
_MINI_COVER_SIZE = 48

# Big touch targets — this is meant to be usable while driving, not just
# glanced at on a desk. A thumb shouldn't need to be precise.
_ROW_HEIGHT = 92
_ROW_COVER_SIZE = 68


class _LibraryScanThread(QThread):
    """Runs music_library.scan_library() off the UI thread. Walking a USB
    drive and reading ID3 tags for every track (mutagen) is blocking disk
    I/O — thousands of tracks worth of it froze/flashed the whole app,
    including the search box, on the first scan after a fresh boot. Track
    is a frozen dataclass with no Qt objects in it, so building the list off
    the main thread is safe; only the result handoff back via `finished`
    touches the GUI, and Qt marshals that onto the main thread automatically."""

    finished_scan = Signal(list)

    def run(self):
        library = music_library.scan_library()
        # Pre-decode every track's cover art here, off the UI thread, so
        # RowWidget construction later (potentially thousands of rows,
        # built eagerly with no list virtualization) hits a warm cache
        # instead of paying for a fresh disk read + JPEG/PNG decode per
        # row — that per-row decode cost was the main reason clicking
        # around felt like it hung the whole app.
        for track in library:
            album_art.warm_cache(track.path)
        self.finished_scan.emit(library)


class RowWidget(QWidget):
    """One row in the browse list: thumbnail (cover art, or an artist's own
    track art standing in as their "photo", or a glyph fallback) plus a
    title/subtitle pair. Used for every list kind (songs, artists,
    playlists, the back-to-artists row) so row height and touch target size
    stay consistent everywhere."""

    def __init__(self, pixmap: QPixmap | None, glyph: str, title: str, subtitle: str = ""):
        super().__init__()
        self.setObjectName("trackRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(14)

        cover = QLabel()
        cover.setObjectName("rowCover")
        cover.setFixedSize(_ROW_COVER_SIZE, _ROW_COVER_SIZE)
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if pixmap is not None:
            cover.setPixmap(
                pixmap.scaled(
                    _ROW_COVER_SIZE,
                    _ROW_COVER_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            cover.setText(glyph)
        layout.addWidget(cover)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("rowTitle")
        text_col.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("rowSubtitle")
            text_col.addWidget(subtitle_label)
        text_col.addStretch(1)
        layout.addLayout(text_col, 1)


class MiniPlayerBar(QWidget):
    """Spotify-style persistent bar showing what's currently playing. Tapping
    anywhere on it (other than the transport buttons) opens the full Now
    Playing screen."""

    expand_requested = Signal()

    def mousePressEvent(self, event):
        self.expand_requested.emit()
        super().mousePressEvent(event)


class TouchLineEdit(QLineEdit):
    """A QLineEdit that signals when it gains/loses focus, so a
    VirtualKeyboard elsewhere in the screen can attach/detach itself —
    there's no physical keyboard in the car, so tapping into search needs
    to bring one up on its own.

    Two prior approaches to this both failed badly enough to need
    replacing:
    - Shelling out to an external "onboard" app — a separate top-level
      window, so tapping a key handed window-manager focus to *onboard*
      itself, keystrokes never reached this field, and the focus bouncing
      back and forth caused visible flashing.
    - Qt's own virtual keyboard (QT_IM_MODULE=qtvirtualkeyboard) — no
      external window, but it hung the whole app on this hardware
      (confirmed: the app stopped responding entirely once it opened).

    This connects to quail_car.virtual_keyboard.VirtualKeyboard instead —
    ordinary QPushButtons in this app's own widget tree, nothing external
    and nothing depending on a separate input-method plugin.
    """

    focused_in = Signal()
    focused_out = Signal()

    def focusInEvent(self, event):
        self.focused_in.emit()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.focused_out.emit()
        super().focusOutEvent(event)


class MusicScreen(QWidget):
    """Quail Music: browses and plays audio files off whatever USB drive is
    currently mounted — playback goes through the mini PC's own audio
    output, not the player's onboard hardware.

    Three browse views share one list widget: All Songs (flat, searchable),
    Artists (drill down into an artist's tracks), and Playlists (stored
    on-device under ~/.local/share/quail_music, plus any .m3u files synced
    directly onto the drive by scripts/music_sync_mp3_player.py). A
    persistent mini-player bar sits below the browse view and expands into
    a full Spotify-style Now Playing screen with cover art and Like/Skip.
    """

    # Mirrors playback state to the outside world so the dashboard's
    # now-playing card can stay in sync without reaching into internals.
    track_changed = Signal(object)  # Track | None
    playing_changed = Signal(bool)
    position_changed = Signal(int, int)  # position_ms, duration_ms
    library_ready = Signal(bool)  # True once a scan finds a non-empty library

    def __init__(self):
        super().__init__()

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_position_changed)

        self._library: list[Track] = []
        self._scan_thread: _LibraryScanThread | None = None
        self._pending_specs: list[tuple] = []
        self._fill_index = 0
        self._fill_timer = QTimer(self)
        self._fill_timer.setSingleShot(True)
        self._fill_timer.timeout.connect(self._fill_next_batch)
        self._path_index: dict[str, Track] = {}
        self._queue: list[Track] = []
        self._current_index = -1

        self._view_mode = "songs"  # songs | artists | artist_tracks | genres | genre_tracks | playlists | playlist_tracks
        self._current_artist: str | None = None
        self._current_genre: str | None = None
        self._current_playlist: str | None = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(10)

        # Created before _build_browse_page() below, since that's where
        # the search box that attaches to this keyboard gets built. Parented
        # to self but deliberately NOT added to root_layout: at 1280x800 the
        # keyboard's ~300px height didn't fit alongside the track list, so
        # laying it out pushed the bottom of the list (and the keyboard
        # itself) off the visible window. Floating it as an absolutely
        # positioned overlay avoids that, and also avoids the whole screen's
        # layout re-flowing on every single key click, which was the
        # laggy-to-type-in behavior.
        self.keyboard = VirtualKeyboard(self)

        self._inner_stack = QStackedWidget()
        root_layout.addWidget(self._inner_stack, 1)

        self._browse_page = self._build_browse_page()
        self._inner_stack.addWidget(self._browse_page)

        self.now_playing_screen = NowPlayingScreen()
        self.now_playing_screen.back_requested.connect(self._collapse_now_playing)
        self.now_playing_screen.prev_requested.connect(self._play_previous)
        self.now_playing_screen.play_pause_requested.connect(self._toggle_play_pause)
        self.now_playing_screen.next_requested.connect(self._play_next)
        self.now_playing_screen.like_requested.connect(self._toggle_like_current)
        self.now_playing_screen.dislike_requested.connect(self._dislike_current)
        self._inner_stack.addWidget(self.now_playing_screen)

        self.mini_player_bar = self._build_mini_player_bar()
        root_layout.addWidget(self.mini_player_bar)
        self.mini_player_bar.setVisible(False)

        # Polling instead of real udev mount events — simpler, no extra
        # dependency, and "notice a plug-in within a few seconds" is plenty
        # responsive for a glove-box USB drive swap.
        self._scan_timer = QTimer(self)
        self._scan_timer.timeout.connect(self._rescan)
        self._scan_timer.start(5000)
        self._set_view_mode("songs")
        self._rescan()

    # ---- layout construction ------------------------------------------------

    def _build_browse_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self.songs_button = QPushButton("All Songs")
        self.artists_button = QPushButton("Artists")
        self.genres_button = QPushButton("Genres")
        self.playlists_button = QPushButton("Playlists")
        for button, mode in (
            (self.songs_button, "songs"),
            (self.artists_button, "artists"),
            (self.genres_button, "genres"),
            (self.playlists_button, "playlists"),
        ):
            button.setObjectName("musicControlButton")
            button.setCheckable(True)
            button.setFixedHeight(40)
            button.clicked.connect(lambda _checked, m=mode: self._set_view_mode(m))
            mode_row.addWidget(button)

        self.eject_button = QPushButton("Eject Drive")
        self.eject_button.setObjectName("musicControlButton")
        self.eject_button.setFixedHeight(40)
        self.eject_button.clicked.connect(self._on_eject_clicked)
        mode_row.addWidget(self.eject_button)

        layout.addLayout(mode_row)

        self.search_box = TouchLineEdit()
        self.search_box.setPlaceholderText("Search artist or song…")
        # Debounced: _refresh_list() rebuilds every visible row from
        # scratch (no list virtualization), so wiring it directly to every
        # keystroke rebuilt the whole list on every single character typed.
        # Restarting a short single-shot timer on each change means only
        # the last keystroke in a burst actually triggers a rebuild.
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.timeout.connect(self._refresh_list)
        self.search_box.textChanged.connect(lambda: self._search_debounce.start(250))
        self.search_box.focused_in.connect(lambda: self._show_keyboard(self.search_box))
        self.search_box.focused_out.connect(self._hide_keyboard)
        layout.addWidget(self.search_box)

        self.track_list = QListWidget()
        self.track_list.setObjectName("musicTrackList")
        # Extended (drag-to-multi-select) selection doesn't work on a
        # touchscreen — a drag is used for scrolling, and rubber-band
        # multi-select from an accidental drag was selecting random ranges
        # of songs. Single tap, single selection.
        self.track_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.track_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.track_list.itemActivated.connect(self._on_item_activated)
        # There's no scrollbar-dragging finger on a touchscreen — grab both
        # gesture types so swiping the list scrolls it, whether the panel's
        # driver reports real touch events or synthesizes mouse events.
        QScroller.grabGesture(self.track_list.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        QScroller.grabGesture(self.track_list.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        layout.addWidget(self.track_list, 1)

        playlist_row = QHBoxLayout()
        playlist_row.setSpacing(8)
        self.shuffle_button = QPushButton("\U0001f500 Shuffle")
        self.new_playlist_button = QPushButton("＋ New Playlist")
        self.add_to_playlist_button = QPushButton("Add to Playlist")
        self.delete_playlist_button = QPushButton("Delete Playlist")
        for button in (
            self.shuffle_button,
            self.new_playlist_button,
            self.add_to_playlist_button,
            self.delete_playlist_button,
        ):
            button.setObjectName("musicControlButton")
            button.setFixedHeight(40)
        self.shuffle_button.clicked.connect(self._shuffle_current_view)
        self.new_playlist_button.clicked.connect(self._create_playlist)
        self.add_to_playlist_button.clicked.connect(self._add_selected_to_playlist)
        self.delete_playlist_button.clicked.connect(self._delete_current_playlist)
        playlist_row.addWidget(self.shuffle_button)
        playlist_row.addWidget(self.new_playlist_button)
        playlist_row.addWidget(self.add_to_playlist_button)
        playlist_row.addWidget(self.delete_playlist_button)
        layout.addLayout(playlist_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("musicStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        return page

    def _build_mini_player_bar(self) -> QWidget:
        bar = MiniPlayerBar()
        bar.setObjectName("miniPlayerBar")
        bar.setFixedHeight(64)
        bar.expand_requested.connect(self._expand_now_playing)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 8, 14, 8)
        layout.setSpacing(12)

        self.mini_cover_label = QLabel()
        self.mini_cover_label.setObjectName("miniPlayerCover")
        self.mini_cover_label.setFixedSize(_MINI_COVER_SIZE, _MINI_COVER_SIZE)
        self.mini_cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.mini_cover_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.mini_title_label = QLabel("No track loaded")
        self.mini_title_label.setObjectName("miniPlayerTitle")
        self.mini_artist_label = QLabel("")
        self.mini_artist_label.setObjectName("miniPlayerArtist")
        text_col.addWidget(self.mini_title_label)
        text_col.addWidget(self.mini_artist_label)
        layout.addLayout(text_col, 1)

        self.mini_play_button = QPushButton("▶")
        self.mini_play_button.setObjectName("miniPlayerButton")
        self.mini_play_button.setFixedSize(40, 40)
        self.mini_play_button.clicked.connect(self._toggle_play_pause)
        layout.addWidget(self.mini_play_button)

        self.mini_next_button = QPushButton("⏭")
        self.mini_next_button.setObjectName("miniPlayerButton")
        self.mini_next_button.setFixedSize(40, 40)
        # clicked() emits a bool "checked" arg — connecting the slot
        # directly would silently pass that as is_skip=False on every tap.
        self.mini_next_button.clicked.connect(lambda: self._play_next())
        layout.addWidget(self.mini_next_button)

        return bar

    def _expand_now_playing(self):
        if self._current_index == -1:
            return
        self._inner_stack.setCurrentWidget(self.now_playing_screen)

    def _collapse_now_playing(self):
        self._inner_stack.setCurrentWidget(self._browse_page)

    # ---- on-screen keyboard overlay ----------------------------------------

    def _show_keyboard(self, line_edit):
        self.keyboard.attach(line_edit)
        self._position_keyboard()
        self.keyboard.raise_()

    def _hide_keyboard(self):
        self.keyboard.detach()

    def _position_keyboard(self):
        height = self.keyboard.sizeHint().height()
        self.keyboard.setGeometry(0, self.height() - height, self.width(), height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_keyboard()

    # ---- library scanning -------------------------------------------------

    def _on_eject_clicked(self):
        # Stop polling immediately — otherwise the 5s timer could fire mid-
        # unmount and briefly try to rescan a volume that's half-detached.
        self._scan_timer.stop()
        # udisksctl refuses to unmount while any process still has a file
        # open on the volume — confirmed via a real "device is busy" error
        # while a track was actively playing. QMediaPlayer keeps the
        # current track's file handle open the whole time it's loaded, even
        # if paused, so it has to be released (not just paused) before an
        # eject can succeed.
        self.player.stop()
        self.player.setSource(QUrl())
        success, message = music_library.eject_active_volume()
        if success:
            self._library = []
            self._path_index = {}
            self.status_label.setText("No music drive detected — plug in your MP3 player")
            self._refresh_list()
            QMessageBox.information(self, "Drive Ejected", message)
        else:
            QMessageBox.warning(self, "Eject Failed", message)
        self._scan_timer.start(5000)

    def _rescan(self):
        # Guard against overlapping scans: the 5s poll timer keeps firing
        # regardless of how long the previous scan is taking, and a scan of
        # a large drive can easily outlast 5 seconds.
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        self._scan_thread = _LibraryScanThread(self)
        self._scan_thread.finished_scan.connect(self._on_scan_finished)
        self._scan_thread.start()

    def _on_scan_finished(self, library: list[Track]):
        # Emitted unconditionally, even when the scan found the same
        # library as before — cheap, idempotent on the dashboard side, and
        # means a screen that missed the first "ready" signal (e.g. wasn't
        # constructed yet) still gets an accurate state on the next poll.
        self.library_ready.emit(bool(library))
        if library == self._library:
            return
        self._library = library
        # Built once per library snapshot instead of once per load_playlist()
        # call — this dict build used to happen from scratch for every
        # single playlist row rendered, on every refresh.
        self._path_index = music_library.build_path_index(library)
        if not self._library:
            self.status_label.setText("No music drive detected — plug in your MP3 player")
        self._refresh_list()

    # ---- view mode / list rendering ---------------------------------------

    def _set_view_mode(self, mode: str):
        self._view_mode = mode
        self._current_artist = None
        self._current_genre = None
        self._current_playlist = None
        self.songs_button.setChecked(mode == "songs")
        self.artists_button.setChecked(mode == "artists")
        self.genres_button.setChecked(mode in ("genres", "genre_tracks"))
        self.playlists_button.setChecked(mode in ("playlists", "playlist_tracks"))
        is_playlists = mode in ("playlists", "playlist_tracks")
        self.new_playlist_button.setVisible(is_playlists)
        self.add_to_playlist_button.setVisible(mode in ("songs", "artist_tracks", "genre_tracks", "playlist_tracks"))
        self.delete_playlist_button.setVisible(mode == "playlist_tracks")
        # Only wherever there's an actual list of tracks to shuffle — not
        # the Artists/Genres/Playlists index views themselves, which list
        # names, not songs.
        self.shuffle_button.setVisible(mode in ("songs", "artist_tracks", "genre_tracks", "playlist_tracks"))
        self.search_box.setVisible(mode in ("songs", "artists", "artist_tracks", "genres", "genre_tracks"))
        self.search_box.clear()
        self._refresh_list()

    def _refresh_list(self):
        self.track_list.clear()
        query = self.search_box.text().strip().lower()

        # Collecting (user_data, art_path, glyph, title, subtitle) tuples
        # here is cheap pure-Python work — no Qt objects get built yet.
        # Actually constructing a RowWidget per entry is deferred to
        # _fill_next_batch() below, spread across several event-loop turns
        # instead of one long synchronous burst. "All Songs" alone can be
        # 2000+ real QWidgets (this list isn't virtualized); building all of
        # them in one go was blocking the whole UI — including buttons
        # unrelated to the list — until the entire browse view finished
        # rendering.
        specs: list[tuple] = []

        if self._view_mode == "songs":
            for track in self._library:
                if query and query not in track.artist.lower() and query not in track.title.lower():
                    continue
                specs.append(self._track_spec(track))

        elif self._view_mode == "artists":
            # Grouped once instead of a fresh full-library scan per artist
            # (was O(distinct artists x library size) — visibly slow once
            # the library grew past a couple thousand tracks).
            by_artist: dict[str, list[Track]] = {}
            for t in self._library:
                by_artist.setdefault(t.artist, []).append(t)
            for artist in sorted(by_artist, key=str.lower):
                if query and query not in artist.lower():
                    continue
                tracks = by_artist[artist]
                count = len(tracks)
                specs.append((
                    ("artist", artist), tracks[0].path, "👤", artist,
                    f"{count} song{'s' if count != 1 else ''}",
                ))

        elif self._view_mode == "artist_tracks":
            specs.append((("back_to_artists", None), None, "‹", _BACK_TO_ARTISTS, ""))
            for track in self._library:
                if track.artist != self._current_artist:
                    continue
                if query and query not in track.title.lower():
                    continue
                specs.append(self._track_spec(track))

        elif self._view_mode == "genres":
            by_genre: dict[str, int] = {}
            for t in self._library:
                by_genre[t.genre] = by_genre.get(t.genre, 0) + 1
            for genre in sorted(by_genre, key=str.lower):
                if query and query not in genre.lower():
                    continue
                count = by_genre[genre]
                specs.append((
                    ("genre", genre), None, "\U0001f3b5", genre,
                    f"{count} song{'s' if count != 1 else ''}",
                ))

        elif self._view_mode == "genre_tracks":
            specs.append((("back_to_genres", None), None, "‹", _BACK_TO_GENRES, ""))
            for track in self._library:
                if track.genre != self._current_genre:
                    continue
                if query and query not in track.title.lower() and query not in track.artist.lower():
                    continue
                specs.append(self._track_spec(track))

        elif self._view_mode == "playlists":
            names = music_library.list_playlist_names()
            for name in names:
                playlist = music_library.load_playlist(name, self._library, self._path_index)
                art_path = playlist.tracks[0].path if playlist.tracks else None
                count = len(playlist.tracks)
                specs.append((
                    ("playlist", name), art_path, "📁", name, f"{count} track{'s' if count != 1 else ''}",
                ))
            if not names:
                self.status_label.setText("No playlists yet — tap “＋ New Playlist”")

        elif self._view_mode == "playlist_tracks":
            playlist = music_library.load_playlist(self._current_playlist, self._library, self._path_index)
            for track in playlist.tracks:
                specs.append(self._track_spec(track))

        self._start_incremental_fill(specs)

    def _track_spec(self, track: Track) -> tuple:
        subtitle = track.artist if track.artist != "Unknown Artist" else ""
        return ("track", track), track.path, "♪", track.title, subtitle

    def _start_incremental_fill(self, specs: list[tuple]):
        self._fill_timer.stop()
        self._pending_specs = specs
        self._fill_index = 0
        self._fill_next_batch()

    _FILL_BATCH_SIZE = 40

    def _fill_next_batch(self):
        end = min(self._fill_index + self._FILL_BATCH_SIZE, len(self._pending_specs))
        for i in range(self._fill_index, end):
            user_data, art_path, glyph, title, subtitle = self._pending_specs[i]
            pixmap = album_art.get_cover_pixmap(art_path) if art_path is not None else None
            self._add_row(user_data, RowWidget(pixmap, glyph, title, subtitle))
        self._fill_index = end
        if self._fill_index < len(self._pending_specs):
            # 0ms singleShot, not a plain function call — yields back to the
            # event loop between batches so queued input (a tap, a search
            # keystroke) gets processed instead of queuing up behind the
            # rest of the list build.
            self._fill_timer.start(0)

    def _add_row(self, user_data: tuple, widget: RowWidget) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, user_data)
        item.setSizeHint(QSize(0, _ROW_HEIGHT))
        self.track_list.addItem(item)
        self.track_list.setItemWidget(item, widget)
        return item

    def _on_item_activated(self, item: QListWidgetItem):
        kind, payload = item.data(Qt.ItemDataRole.UserRole)
        if kind == "track":
            self._play_queue_from_current_view()
            # Indexed against the queue built above (== _current_view_tracks(),
            # sourced from _pending_specs) rather than the QListWidget's
            # realized items — rows fill in incrementally now (see
            # _fill_next_batch), so the widget list can be a partial subset
            # of the full filtered view at the moment a tap lands.
            index = self._queue.index(payload)
            self._play_index(index)
        elif kind == "artist":
            self._current_artist = payload
            self._view_mode = "artist_tracks"
            self.search_box.clear()
            self.add_to_playlist_button.setVisible(True)
            self.delete_playlist_button.setVisible(False)
            self.shuffle_button.setVisible(True)
            self._refresh_list()
        elif kind == "back_to_artists":
            self._set_view_mode("artists")
        elif kind == "genre":
            self._current_genre = payload
            self._view_mode = "genre_tracks"
            self.search_box.clear()
            self.add_to_playlist_button.setVisible(True)
            self.delete_playlist_button.setVisible(False)
            self.shuffle_button.setVisible(True)
            self._refresh_list()
        elif kind == "back_to_genres":
            self._set_view_mode("genres")
        elif kind == "playlist":
            self._current_playlist = payload
            self._view_mode = "playlist_tracks"
            self.playlists_button.setChecked(True)
            self.new_playlist_button.setVisible(False)
            self.add_to_playlist_button.setVisible(True)
            self.delete_playlist_button.setVisible(True)
            self.shuffle_button.setVisible(True)
            self._refresh_list()

    def _current_view_tracks(self) -> list[Track]:
        # Sourced from _pending_specs (the full filtered view, computed
        # synchronously in _refresh_list) rather than the QListWidget's
        # realized items, which may still be a partial subset while a batch
        # fill is in progress (see _fill_next_batch).
        return [spec[0][1] for spec in self._pending_specs if spec[0][0] == "track"]

    def _play_queue_from_current_view(self):
        self._queue = self._current_view_tracks()

    def _shuffle_and_play(self, tracks: list[Track]):
        if not tracks:
            return
        shuffled = tracks.copy()
        random.shuffle(shuffled)
        self._queue = shuffled
        self._current_index = -1
        self._play_index(0)

    def _shuffle_current_view(self):
        self._shuffle_and_play(self._current_view_tracks())

    def shuffle_all(self):
        """Public — the dashboard's now-playing card calls this for its
        "shuffle all songs" idle-state button, independent of whatever
        browse view Music itself currently has open."""
        self._shuffle_and_play(self._library)

    def play_last_playlist(self):
        """Public — the dashboard's "Play Last Playlist" quick action.
        Prefers resuming whatever's already loaded (the common case: it's
        just paused), falls back to replaying the last playlist actually
        browsed into this session, and only shuffles the whole library if
        neither of those exist yet."""
        if self._queue and self._current_index != -1:
            if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self._toggle_play_pause()
            return
        if self._current_playlist:
            playlist = music_library.load_playlist(self._current_playlist, self._library, self._path_index)
            if playlist.tracks:
                self._shuffle_and_play(playlist.tracks)
                return
        self.shuffle_all()

    def _selected_tracks(self) -> list[Track]:
        tracks = []
        for item in self.track_list.selectedItems():
            kind, payload = item.data(Qt.ItemDataRole.UserRole)
            if kind == "track":
                tracks.append(payload)
        return tracks

    # ---- playlist management -----------------------------------------------

    def _create_playlist(self):
        name, ok = QInputDialog.getText(self, "New Playlist", "Playlist name:")
        name = name.strip()
        if not ok or not name:
            return
        music_library.save_playlist(Playlist(name=name, tracks=[]))
        self._refresh_list()

    def _add_selected_to_playlist(self):
        tracks = self._selected_tracks()
        if not tracks:
            QMessageBox.information(self, "Add to Playlist", "Select a track first.")
            return
        names = music_library.list_playlist_names()
        if not names:
            QMessageBox.information(self, "Add to Playlist", "Create a playlist first.")
            return
        name, ok = QInputDialog.getItem(self, "Add to Playlist", "Playlist:", names, editable=False)
        if not ok:
            return
        playlist = music_library.load_playlist(name, self._library, self._path_index)
        existing_paths = {t.path for t in playlist.tracks}
        for track in tracks:
            if track.path not in existing_paths:
                playlist.tracks.append(track)
        music_library.save_playlist(playlist)
        self.status_label.setText(f"Added {len(tracks)} track(s) to “{name}”")

    def _delete_current_playlist(self):
        if not self._current_playlist:
            return
        music_library.delete_playlist(self._current_playlist)
        self._set_view_mode("playlists")

    # ---- like / dislike -----------------------------------------------------

    def _current_track(self) -> Track | None:
        if 0 <= self._current_index < len(self._queue):
            return self._queue[self._current_index]
        return None

    def _is_liked(self, track: Track) -> bool:
        liked = music_library.load_playlist(_LIKED_PLAYLIST_NAME, self._library, self._path_index)
        return any(t.path == track.path for t in liked.tracks)

    def _toggle_like_current(self):
        track = self._current_track()
        if track is None:
            return
        liked = music_library.load_playlist(_LIKED_PLAYLIST_NAME, self._library, self._path_index)
        now_liked = not any(t.path == track.path for t in liked.tracks)
        if now_liked:
            liked.tracks.append(track)
        else:
            liked.tracks = [t for t in liked.tracks if t.path != track.path]
        music_library.save_playlist(liked)
        self.now_playing_screen.set_liked(self._is_liked(track))
        feedback_log.append_event("like" if now_liked else "unlike", track)

    def _dislike_current(self):
        track = self._current_track()
        if track is not None:
            feedback_log.append_event("dislike", track)
        # Dislike is itself the negative signal — don't also log a separate
        # "skip" for the same abandonment.
        self._play_next(is_skip=False)

    # ---- playback -----------------------------------------------------------

    def _play_index(self, index: int):
        if not (0 <= index < len(self._queue)):
            return
        self._current_index = index
        track = self._queue[index]
        self.player.setSource(QUrl.fromLocalFile(str(track.path)))
        self.player.play()
        self._update_now_playing_ui(track, is_playing=True)

    def _toggle_play_pause(self):
        if self._current_index == -1:
            if not self._queue:
                self._play_queue_from_current_view()
            if self._queue:
                self._play_index(0)
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self._set_playing_ui(False)
        else:
            self.player.play()
            self._set_playing_ui(True)

    def _play_next(self, is_skip: bool = True):
        # is_skip distinguishes a manual "next" tap (real skip signal, worth
        # feeding back) from advancing because the track just finished
        # naturally (see _on_media_status_changed) — those aren't the same
        # thing and shouldn't both count as the user rejecting the track.
        if is_skip:
            track = self._current_track()
            if track is not None:
                feedback_log.append_event("skip", track)
        if self._queue:
            self._play_index((self._current_index + 1) % len(self._queue))

    def _play_previous(self):
        if self._queue:
            self._play_index((self._current_index - 1) % len(self._queue))

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._play_next(is_skip=False)

    def _on_position_changed(self, _value: int):
        # Both positionChanged(int) and durationChanged(int) land here —
        # the dashboard's progress bar needs both together to draw a
        # correct fraction, and re-reading player.position()/.duration()
        # directly (rather than trusting whichever single value the
        # signal that fired carried) keeps the two always in sync.
        self.position_changed.emit(self.player.position(), self.player.duration())

    def _update_now_playing_ui(self, track: Track, is_playing: bool):
        self.mini_player_bar.setVisible(True)
        self.mini_title_label.setText(track.title)
        self.mini_artist_label.setText(track.artist)
        pixmap = album_art.get_cover_pixmap(track.path)
        if pixmap is not None:
            self.mini_cover_label.setPixmap(
                pixmap.scaled(
                    _MINI_COVER_SIZE,
                    _MINI_COVER_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.mini_cover_label.setPixmap(QPixmap())
            self.mini_cover_label.setText("♪")

        self.now_playing_screen.set_track(track)
        self.now_playing_screen.set_liked(self._is_liked(track))
        self.track_changed.emit(track)
        self._set_playing_ui(is_playing)

    def _set_playing_ui(self, is_playing: bool):
        self.mini_play_button.setText("⏸" if is_playing else "▶")
        self.now_playing_screen.set_playing(is_playing)
        self.playing_changed.emit(is_playing)

    def toggle_play_pause(self):
        self._toggle_play_pause()

    def play_next(self):
        self._play_next()

    def play_previous(self):
        self._play_previous()

    def seek(self, position_ms: int):
        self.player.setPosition(position_ms)
