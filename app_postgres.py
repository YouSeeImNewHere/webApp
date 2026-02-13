"""Compatibility entrypoint.

This keeps your original uvicorn target working:

    uvicorn app_postgres:app --reload

All actual app code now lives in the app/ package.
"""

from app.main import app  # noqa: F401
