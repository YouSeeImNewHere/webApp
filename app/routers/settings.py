from __future__ import annotations

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import with_db_cursor

router = APIRouter()

# =============================================================================
# Settings (Postgres) — ported from settings.py
# =============================================================================

# -----------------------------
# Models (same API)
# -----------------------------
class RateUpsert(BaseModel):
    account_id: int
    rate_percent: float  # user enters 3.54 (percent)
    effective_date: Optional[str] = None  # "YYYY-MM-DD" (optional)
    note: Optional[str] = None

class SaveLayoutBody(BaseModel):
    key: str
    layout: Dict[str, Any]

class SaveLESProfileBody(BaseModel):
    key: str = "default"
    profile: Dict[str, Any]

class SavingsGoalIn(BaseModel):
    mode: str  # "percent" | "amount"
    value: float

# -----------------------------
# Table ensure helpers (Postgres)
# -----------------------------
def _ensure_app_settings_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        conn.commit()

def _ensure_ui_layout_table_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ui_layout (
              key TEXT PRIMARY KEY,
              layout_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        conn.commit()

def _ensure_les_profile_table_pg():
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS les_profile (
              key TEXT PRIMARY KEY,
              profile_json TEXT NOT NULL DEFAULT '{}',
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        conn.commit()

def _ensure_interest_rates_table_pg():
    # Your DB screenshot shows interest_rates exists, but this makes it robust.
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS interest_rates (
              id SERIAL PRIMARY KEY,
              account_id INT NOT NULL,
              apr DOUBLE PRECISION NOT NULL,
              effective_date DATE NOT NULL,
              note TEXT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        # helpful uniqueness to prevent dupes per account/day
        cur.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname='public'
                  AND indexname='ux_interest_rates_account_day'
              ) THEN
                CREATE UNIQUE INDEX ux_interest_rates_account_day
                  ON interest_rates(account_id, effective_date);
              END IF;
            END $$;
            """
        )
        conn.commit()

