"""One-time interactive Garmin Connect login.

Run this manually (not via cron) once, from an interactive terminal:

    .venv/bin/python scripts/garmin_login_setup.py

It logs in with your Garmin account (prompting for an MFA code if Garmin
asks for one) and saves session tokens to GARMIN_TOKENSTORE_PATH (defaults to
~/.garminconnect_tokens). scripts/garmin_sync_runs.py then reuses those saved
tokens non-interactively — Garmin's tokens are long-lived and auto-refresh, so
this should only need to be re-run if the token store is deleted or Garmin
invalidates the session (e.g. after a password change).

Nothing is written to .env or the git repo — the email/password you enter
here are only used for this one login call and are never persisted; only the
resulting session tokens are saved to disk, outside the repo.
"""
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from garminconnect import Garmin

TOKENSTORE_PATH = os.getenv("GARMIN_TOKENSTORE_PATH") or str(Path.home() / ".garminconnect_tokens")


def main() -> None:
    email = input("Garmin Connect email: ").strip()
    password = getpass.getpass("Garmin Connect password: ")

    garmin = Garmin(email=email, password=password, return_on_mfa=True)
    result1, result2 = garmin.login(tokenstore=TOKENSTORE_PATH)

    if result1 == "needs_mfa":
        mfa_code = input("Enter the MFA code Garmin sent you: ").strip()
        garmin.resume_login(result2, mfa_code)
        garmin.client.dump(TOKENSTORE_PATH)

    print(f"Login successful. Tokens saved to {TOKENSTORE_PATH}")
    print("scripts/garmin_sync_runs.py can now run non-interactively via cron.")


if __name__ == "__main__":
    main()
