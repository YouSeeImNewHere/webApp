#!/bin/bash
# Fired by launchd whenever /Volumes changes (see
# ~/Library/LaunchAgents/com.quail.musicsync.plist). Checks whether the
# "SSD MP3" drive is actually the thing that just mounted, and if so runs
# the Jellyfin sync — this is what makes plugging the player in "just work"
# with no typing.
#
# The Jellyfin API key lives in ~/.config/quail_music/env (NOT in this repo)
# so it never ends up in git history.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOLUME_NAME="${MP3_PLAYER_VOLUME_NAME:-SSD MP3}"
# Second volume that's normally along for the ride (e.g. another
# partition on the same physical drive) — the sync window's "OK and
# Eject" button ejects both, best-effort, so it's safe to unplug right
# after clicking even if only one of the two is actually connected today.
SECONDARY_VOLUME_NAME="${MP3_PLAYER_SECONDARY_VOLUME_NAME:-Y2}"
MOUNT_PATH="/Volumes/${VOLUME_NAME}"
LOCK_FILE="/tmp/quail_music_sync.lock"
ENV_FILE="$HOME/.config/quail_music/env"

if [ ! -d "$MOUNT_PATH" ]; then
    exit 0
fi

if [ -e "$LOCK_FILE" ]; then
    exit 0
fi
touch "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# Launched immediately — before the mount-settle sleep below, before the
# API key check, before anything else — so it's the very first thing the
# user sees once the drive is actually plugged in, including error paths
# like a missing JELLYFIN_API_KEY. It only picks up log lines written
# *after* it opens (reads the log's current size as its starting offset,
# see music_sync_window.py), so it needs to be running before anything
# else writes to the log this run, not after.
"$REPO_DIR/.venv/bin/python3" "$REPO_DIR/scripts/music_sync_window.py" "$VOLUME_NAME" "$SECONDARY_VOLUME_NAME" &
sleep 0.5

echo "$(date): $VOLUME_NAME detected, syncing…"

# Give macOS a moment to finish mounting before we start reading/writing.
sleep 3

if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

if [ -z "${JELLYFIN_API_KEY:-}" ]; then
    echo "$(date): JELLYFIN_API_KEY not set — create $ENV_FILE" >&2
    exit 1
fi

export JELLYFIN_API_KEY
"$REPO_DIR/.venv/bin/python3" "$REPO_DIR/scripts/music_sync_mp3_player.py" "$MOUNT_PATH"
echo "$(date): sync finished"

# Best-effort — feedback events (like/dislike/skip logged by Quail Music in
# the car) shouldn't block the playlist sync above if this fails or the
# token isn't set yet.
if [ -n "${LISTENBRAINZ_TOKEN:-}" ]; then
    echo "$(date): submitting feedback events…"
    export LISTENBRAINZ_TOKEN
    "$REPO_DIR/.venv/bin/python3" "$REPO_DIR/scripts/music_feedback_sync.py" "$MOUNT_PATH" || \
        echo "$(date): feedback sync failed, will retry next time" >&2
else
    echo "$(date): LISTENBRAINZ_TOKEN not set — skipping feedback sync" >&2
fi

# Best-effort, same reasoning as feedback sync above — genre lookups
# (quail_car/music_library.py reads the result) shouldn't block the
# playlist sync if MusicBrainz is slow/unreachable this run.
echo "$(date): looking up genres for new tracks…"
"$REPO_DIR/.venv/bin/python3" "$REPO_DIR/scripts/music_genre_sync.py" "$MOUNT_PATH" || \
    echo "$(date): genre sync failed, will retry next time" >&2

# The window's actual "we're done, show the summary and enable OK" signal
# — everything above is best-effort and can fail without stopping the
# script (the || echo fallbacks), so this always runs and always fires,
# regardless of which steps above succeeded.
echo "$(date): all done"
