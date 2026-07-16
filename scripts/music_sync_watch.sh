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

echo "$(date): $VOLUME_NAME detected, syncing…"
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
