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

# Environment flags
IS_RENDER = bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_SERVICE_ID"))
IS_PROD = os.getenv("ENV", "").lower() == "prod"

# App constants
MAX_TRANSFER_WINDOW_DAYS = 10
CATEGORY_RULES_TABLE = "categoryrules"
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# UI constants
CREDIT_UTILIZATION_CAP = 0.30  # same as home.js
