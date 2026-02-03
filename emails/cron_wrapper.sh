#!/usr/bin/env bash
set -u

JOB_NAME="emailFetch"
START_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

LOG_FILE="$(mktemp)"
python /opt/render/project/src/emails/emailFetch.py >"$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
  # last ~8k chars so you don't blow up DB/UI
  LOG_TAIL="$(python - <<PY
import pathlib
p = pathlib.Path("$LOG_FILE")
txt = p.read_text(errors="replace")
print(txt[-8000:])
PY
)"

  # Dedupe key should be unique per failure run
  DEDUPE_KEY="cron:${JOB_NAME}:${START_UTC}:exit${EXIT_CODE}"

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
fi

rm -f "$LOG_FILE"
exit "$EXIT_CODE"
