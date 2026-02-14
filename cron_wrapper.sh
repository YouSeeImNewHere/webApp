#!/usr/bin/env bash
set -uo pipefail

JOB_NAME="emailFetch"
START_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
LOCK_DIR="/tmp/${JOB_NAME}.lockdir"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[$START_UTC] ${JOB_NAME}: previous run still active; skipping overlap."
  exit 0
fi

LOG_FILE="$(mktemp)"
cleanup() {
  rm -f "$LOG_FILE"
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

if [ -d /opt/render/project/src ]; then
  cd /opt/render/project/src
else
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  cd "$SCRIPT_DIR"
fi
python -m emails.emailFetch 2>&1 | tee "$LOG_FILE"
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
  LOG_TAIL="$(tail -c 8000 "$LOG_FILE" 2>/dev/null || true)"

  DEDUPE_KEY="cron:${JOB_NAME}:${START_UTC}:exit${EXIT_CODE}"

  if [ -n "${WEBAPP_URL:-}" ] && [ -n "${NOTIF_SECRET:-}" ]; then
    curl -sS -X POST "$WEBAPP_URL/notifications/push" \
      -H "Content-Type: application/json" \
      -H "X-Notif-Secret: $NOTIF_SECRET" \
      --data-binary @- <<JSON
{
  "kind": "cron_fail",
  "dedupe_key": "$DEDUPE_KEY",
  "subject": "Cron FAILED: $JOB_NAME (exit $EXIT_CODE)",
  "sender": "Render Cron",
  "body": "Start (UTC): $START_UTC\\nExit: $EXIT_CODE\\n\\n--- LOG (tail) ---\\n$LOG_TAIL"
}
JSON
  else
    echo "[$START_UTC] ${JOB_NAME}: failed (exit $EXIT_CODE), notification skipped (WEBAPP_URL/NOTIF_SECRET not set)."
  fi
fi

exit "$EXIT_CODE"
