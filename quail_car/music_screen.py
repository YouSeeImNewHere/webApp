from __future__ import annotations

from PySide6.QtCore import QSize, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
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

_BACK_TO_ARTISTS = "‹ Back to Artists"
_LIKED_PLAYLIST_NAME = "Liked Songs"
_MINI_COVER_SIZE = 48

# Big touch targets — this is meant to be usable while driving, not just
# glanced at on a desk. A thumb shouldn't need to be precise.
_ROW_HEIGHT = 92
_ROW_COVER_SIZE = 68


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
    """A QLineEdit that pops Qt's own virtual keyboard on focus — there's no
    physical keyboard in the car, so tapping into search needs to bring one
    up itself.

    This used to shell out to the external "onboard" app, but that's a
    separate top-level window: tapping a key on it handed window-manager
    focus to *onboard*, so keystrokes never reached this field, and the
    focus bouncing back and forth caused visible flashing. Qt's built-in
    virtual keyboard (enabled via QT_IM_MODULE=qtvirtualkeyboard in
    main.py) renders as an overlay inside this app's own window instead —
    no separate window, no focus stealing, keys land directly in whatever's
    focused.
    """

    def focusInEvent(self, event):
        QGuiApplication.inputMethod().show()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        QGuiApplication.inputMethod().hide()
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

    def __init__(self):
        super().__init__()

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

        self._library: list[Track] = []
        self._path_index: dict[str, Track] = {}
        self._queue: list[Track] = []
        self._current_index = -1

        self._view_mode = "songs"  # songs | artists | artist_tracks | playlists | playlist_tracks
        self._current_artist: str | None = None
        self._current_playlist: str | None = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(10)

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
        self.playlists_button = QPushButton("Playlists")
        for button, mode in (
            (self.songs_button, "songs"),
            (self.artists_button, "artists"),
            (self.playlists_button, "playlists"),
        ):
            button.setObjectName("musicControlButton")
            button.setCheckable(True)
            button.setFixedHeight(40)
            button.clicked.connect(lambda _checked, m=mode: self._set_view_mode(m))
            mode_row.addWidget(button)
        layout.addLayout(mode_row)

        self.search_box = TouchLineEdit()
        self.search_box.setPlaceholderText("Search artist or song…")
        self.search_box.textChanged.connect(self._refresh_list)
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
        self.new_playlist_button = QPushButton("＋ New Playlist")
        self.add_to_playlist_button = QPushButton("Add to Playlist")
        self.delete_playlist_button = QPushButton("Delete Playlist")
        for button in (
            self.new_playlist_button,
            self.add_to_playlist_button,
            self.delete_playlist_button,
        ):
            button.setObjectName("musicControlButton")
            button.setFixedHeight(40)
        self.new_playlist_button.clicked.connect(self._create_playlist)
        self.add_to_playlist_button.clicked.connect(self._add_selected_to_playlist)
        self.delete_playlist_button.clicked.connect(self._delete_current_playlist)
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

    # ---- library scanning -------------------------------------------------

    def _rescan(self):
        library = music_library.scan_library()
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
        self._current_playlist = None
        self.songs_button.setChecked(mode == "songs")
        self.artists_button.setChecked(mode == "artists")
        self.playlists_button.setChecked(mode in ("playlists", "playlist_tracks"))
        is_playlists = mode in ("playlists", "playlist_tracks")
        self.new_playlist_button.setVisible(is_playlists)
        self.add_to_playlist_button.setVisible(mode in ("songs", "artist_tracks", "playlist_tracks"))
        self.delete_playlist_button.setVisible(mode == "playlist_tracks")
        self.search_box.setVisible(mode in ("songs", "artists", "artist_tracks"))
        self.search_box.clear()
        self._refresh_list()

    def _refresh_list(self):
        self.track_list.clear()
        query = self.search_box.text().strip().lower()

        if self._view_mode == "songs":
            for track in self._library:
                if query and query not in track.artist.lower() and query not in track.title.lower():
                    continue
                self._add_track_item(track)

        elif self._view_mode == "artists":
            artists = sorted({t.artist for t in self._library}, key=str.lower)
            for artist in artists:
                if query and query not in artist.lower():
                    continue
                count = sum(1 for t in self._library if t.artist == artist)
                pixmap = album_art.get_artist_pixmap(artist, self._library)
                self._add_row(
                    ("artist", artist),
                    RowWidget(pixmap, "👤", artist, f"{count} song{'s' if count != 1 else ''}"),
                )

        elif self._view_mode == "artist_tracks":
            self._add_row(
                ("back_to_artists", None),
                RowWidget(None, "‹", _BACK_TO_ARTISTS),
            )
            for track in self._library:
                if track.artist != self._current_artist:
                    continue
                if query and query not in track.title.lower():
                    continue
                self._add_track_item(track)

        elif self._view_mode == "playlists":
            names = music_library.list_playlist_names()
            for name in names:
                playlist = music_library.load_playlist(name, self._library, self._path_index)
                pixmap = album_art.get_cover_pixmap(playlist.tracks[0].path) if playlist.tracks else None
                count = len(playlist.tracks)
                self._add_row(
                    ("playlist", name),
                    RowWidget(pixmap, "📁", name, f"{count} track{'s' if count != 1 else ''}"),
                )
            if not names:
                self.status_label.setText("No playlists yet — tap “＋ New Playlist”")

        elif self._view_mode == "playlist_tracks":
            playlist = music_library.load_playlist(self._current_playlist, self._library, self._path_index)
            for track in playlist.tracks:
                self._add_track_item(track)

    def _add_row(self, user_data: tuple, widget: RowWidget) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, user_data)
        item.setSizeHint(QSize(0, _ROW_HEIGHT))
        self.track_list.addItem(item)
        self.track_list.setItemWidget(item, widget)
        return item

    def _add_track_item(self, track: Track):
        pixmap = album_art.get_cover_pixmap(track.path)
        subtitle = track.artist if track.artist != "Unknown Artist" else ""
        self._add_row(("track", track), RowWidget(pixmap, "♪", track.title, subtitle))

    def _on_item_activated(self, item: QListWidgetItem):
        kind, payload = item.data(Qt.ItemDataRole.UserRole)
        if kind == "track":
            self._play_queue_from_current_view()
            index = [self.track_list.item(i).data(Qt.ItemDataRole.UserRole)[1]
                     for i in range(self.track_list.count())
                     if self.track_list.item(i).data(Qt.ItemDataRole.UserRole)[0] == "track"].index(payload)
            self._play_index(index)
        elif kind == "artist":
            self._current_artist = payload
            self._view_mode = "artist_tracks"
            self.search_box.clear()
            self.add_to_playlist_button.setVisible(True)
            self.delete_playlist_button.setVisible(False)
            self._refresh_list()
        elif kind == "back_to_artists":
            self._set_view_mode("artists")
        elif kind == "playlist":
            self._current_playlist = payload
            self._view_mode = "playlist_tracks"
            self.playlists_button.setChecked(True)
            self.new_playlist_button.setVisible(False)
            self.add_to_playlist_button.setVisible(True)
            self.delete_playlist_button.setVisible(True)
            self._refresh_list()

    def _current_view_tracks(self) -> list[Track]:
        tracks = []
        for i in range(self.track_list.count()):
            data = self.track_list.item(i).data(Qt.ItemDataRole.UserRole)
            if data[0] == "track":
                tracks.append(data[1])
        return tracks

    def _play_queue_from_current_view(self):
        self._queue = self._current_view_tracks()

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
        self._set_playing_ui(is_playing)

    def _set_playing_ui(self, is_playing: bool):
        self.mini_play_button.setText("⏸" if is_playing else "▶")
        self.now_playing_screen.set_playing(is_playing)
