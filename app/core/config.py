from __future__ import annotations

import os
import re
import time
from dotenv import load_dotenv

load_dotenv()

BUILD_ID = str(int(time.time()))

# Secrets / gates
NOTIF_SECRET = os.getenv("NOTIF_SECRET", "")
WIDGET_SECRET = os.getenv("WIDGET_SECRET", "")  # set this in Render env vars
SESSION_SECRET = (os.getenv("SESSION_SECRET", "") or "").strip()
APP_PASSWORD = (os.getenv("APP_PASSWORD", "") or "").strip().strip('"').strip("'")
WEBAPP_URL = (os.getenv("WEBAPP_URL", "") or "").strip().rstrip("/")
GOOGLE_CLIENT_ID = (os.getenv("GOOGLE_CLIENT_ID", "") or "").strip()
GOOGLE_CLIENT_SECRET = (os.getenv("GOOGLE_CLIENT_SECRET", "") or "").strip()
GOOGLE_OAUTH_REDIRECT_URI = (os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "") or "").strip()
GOOGLE_PUBSUB_TOPIC = (os.getenv("GOOGLE_PUBSUB_TOPIC", "") or "").strip()
MULTI_TENANT_ENABLED = (os.getenv("MULTI_TENANT_ENABLED", "false") or "").lower() in ("1", "true", "yes")
OWNER_GOOGLE_EMAIL = (os.getenv("OWNER_GOOGLE_EMAIL", "") or "").strip().lower()
try:
    SESSION_MAX_AGE_DAYS = max(1, int(os.getenv("SESSION_MAX_AGE_DAYS", "30")))
except Exception:
    SESSION_MAX_AGE_DAYS = 30

# Environment flags
IS_RENDER = bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_SERVICE_ID"))
IS_PROD = os.getenv("ENV", "").lower() == "prod"

# App constants
MAX_TRANSFER_WINDOW_DAYS = 10
CATEGORY_RULES_TABLE = "categoryrules"
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# UI constants
CREDIT_UTILIZATION_CAP = 0.30  # same as home.js
