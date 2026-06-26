#!/usr/bin/env python3
"""
Import Maintenance.csv (exported from Numbers) into Neon.

Sections it handles:
  1. Fuel fillup records    — Dates / Mileage / Difference / Gas got / MPG
  2. Fluid status table     — Engine oil / coolant / transmission / brake fluid
  3. Periodic items table   — Rotate tires / spark plugs / brakes / etc.
  4. Oil change history     — two-column Changed (time) / Changed (mi) blocks
  5. Current mileage        — final row

Usage (from the webApp directory):
    python scripts/import_vehicle_csv.py /Users/trevinjc/Documents/Maintenance.csv
    python scripts/import_vehicle_csv.py /Users/trevinjc/Documents/Maintenance.csv --tenant-id 1 --dry-run
"""

import argparse
import csv
import os
import sys
from datetime import date, datetime

from dotenv import load_dotenv

load_dotenv()

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("Install psycopg: pip install 'psycopg[binary]'")
    sys.exit(1)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL not set in .env")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_float(raw: str) -> float | None:
    raw = raw.strip().replace(",", "")
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def parse_int(raw: str) -> int | None:
    v = parse_float(raw)
    return int(v) if v is not None else None


def cell(row: list[str], idx: int) -> str:
    return row[idx].strip() if idx < len(row) else ""


# ---------------------------------------------------------------------------
# Section detection helpers
# ---------------------------------------------------------------------------

def is_fuel_header(row: list[str]) -> bool:
    return len(row) >= 4 and row[0].strip().lower() == "dates"


def looks_like_fuel_row(row: list[str]) -> bool:
    # First cell is a date like 3/19/22
    return parse_date(cell(row, 0)) is not None and len(row) >= 4


def is_fluid_status_header(row: list[str]) -> bool:
    # , Monthly check, Changed (mi), Changed (time), Frequency (mi), ...
    return len(row) >= 3 and row[1].strip().lower() == "monthly check"


def is_periodic_header(row: list[str]) -> bool:
    # , Changed (mi), Frequency (mi), Overdue?
    return (
        len(row) >= 3
        and row[0].strip() == ""
        and row[1].strip().lower() in ("changed (mi)", "changed(mi)")
        and row[2].strip().lower() in ("frequency (mi)", "frequency(mi)")
    )


def is_service_history_header(row: list[str]) -> bool:
    # Changed (time), Changed (mi)
    return (
        len(row) >= 2
        and row[0].strip().lower() == "changed (time)"
        and row[1].strip().lower() in ("changed (mi)", "changed(mi)")
        and row[0].strip() != ""  # not the periodic header
    )


def is_current_mileage_row(row: list[str]) -> bool:
    return len(row) >= 2 and "current mileage" in row[0].strip().lower()


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def parse_fuel_records(rows: list[list[str]]) -> list[dict]:
    records = []
    for row in rows:
        if not looks_like_fuel_row(row):
            break
        dt = parse_date(cell(row, 0))
        mileage = parse_int(cell(row, 1))
        miles_since = parse_float(cell(row, 2))
        gallons = parse_float(cell(row, 3))
        mpg_raw = parse_float(cell(row, 4)) if len(row) > 4 else None

        if gallons is None or gallons == 0:
            continue  # skip zero-gallon / incomplete rows

        mpg = mpg_raw if mpg_raw and 0 < mpg_raw < 150 else None

        records.append({
            "date": dt,
            "mileage": mileage or 0,
            "miles_since_last": miles_since,
            "gallons": gallons,
            "mpg": mpg,
        })
    return records


def parse_fluid_status(rows: list[list[str]]) -> list[dict]:
    # Engine oil,FALSE,"179,004",5/30/26,"3,000",52w,No
    # cols: name / monthly_check / changed_mi / changed_time / freq_mi / freq_time / overdue
    items = []
    for row in rows:
        name = cell(row, 0)
        if not name or name.lower() in ("", "monthly check"):
            break
        changed_date = parse_date(cell(row, 3))
        changed_mi = parse_int(cell(row, 2))
        freq_mi_raw = cell(row, 4)
        freq_days = None
        try:
            freq_mi = parse_int(freq_mi_raw)
            # rough days: assume 12,000 mi/yr → miles / (12000/365)
            if freq_mi and freq_mi > 0:
                freq_days = max(30, int(freq_mi / 12000 * 365))
        except Exception:
            pass

        items.append({
            "name": name,
            "last_checked_date": changed_date,
            "periodicity_days": freq_days or 365,
        })
    return items


def parse_periodic_items(rows: list[list[str]]) -> list[dict]:
    # , Changed (mi), Frequency (mi), Overdue?
    # Rotate tires, 166192, "7,500", Yes
    items = []
    for row in rows:
        name = cell(row, 0)
        if not name:
            break
        changed_mi = parse_int(cell(row, 1))
        freq_mi = parse_int(cell(row, 2))
        freq_days = max(30, int(freq_mi / 12000 * 365)) if freq_mi else 365

        items.append({
            "name": name.strip().rstrip(),
            "last_checked_date": None,
            "periodicity_days": freq_days,
        })
    return items


def parse_service_history(rows: list[list[str]], label: str) -> list[dict]:
    # Changed (time), Changed (mi)
    # 6/19/23, "156,288"
    records = []
    for row in rows:
        dt = parse_date(cell(row, 0))
        mileage = parse_int(cell(row, 1))
        if dt is None and mileage is None:
            break
        if not dt and not mileage:
            break
        records.append({
            "type_name": label,
            "date": dt,
            "mileage": mileage or 0,
        })
    return records


# ---------------------------------------------------------------------------
# Main parse pass
# ---------------------------------------------------------------------------

FLUID_LABEL_MAP = {
    "engine oil": "Oil Change",
    "engine coolant": "Coolant Change",
    "transmission fluid": "Transmission Fluid Change",
    "brake fluid": "Brake Fluid Change",
}

def parse_csv(path: str) -> dict:
    with open(path, newline="", encoding="utf-8-sig") as f:
        raw = list(csv.reader(f))

    result = {
        "fuel_records": [],
        "maintenance_records": [],
        "inspection_items": [],
        "current_mileage": None,
    }

    i = 0
    service_history_labels = []  # track what the service history blocks are for

    while i < len(raw):
        row = raw[i]

        if not any(c.strip() for c in row):
            i += 1
            continue

        if is_current_mileage_row(row):
            result["current_mileage"] = parse_int(cell(row, 1))
            i += 1
            continue

        if is_fuel_header(row):
            i += 1
            fuel_rows = []
            while i < len(raw) and looks_like_fuel_row(raw[i]):
                fuel_rows.append(raw[i])
                i += 1
            result["fuel_records"] = parse_fuel_records(fuel_rows)
            continue

        if is_fluid_status_header(row):
            i += 1
            fluid_rows = []
            while i < len(raw) and len(raw[i]) > 0 and raw[i][0].strip() and not is_service_history_header(raw[i]) and not is_periodic_header(raw[i]):
                if any(c.strip() for c in raw[i]):
                    fluid_rows.append(raw[i])
                i += 1
            items = parse_fluid_status(fluid_rows)
            result["inspection_items"].extend(items)
            # Remember the fluid names in order for service history blocks
            service_history_labels = [
                FLUID_LABEL_MAP.get(fi["name"].lower(), fi["name"] + " Change")
                for fi in items
            ]
            continue

        if is_periodic_header(row):
            i += 1
            periodic_rows = []
            while i < len(raw) and len(raw[i]) > 0 and raw[i][0].strip() and not is_service_history_header(raw[i]):
                if any(c.strip() for c in raw[i]):
                    periodic_rows.append(raw[i])
                i += 1
            result["inspection_items"].extend(parse_periodic_items(periodic_rows))
            continue

        if is_service_history_header(row):
            # Pop the next label from the fluid list (in order)
            label = service_history_labels.pop(0) if service_history_labels else "Service"
            i += 1
            hist_rows = []
            while i < len(raw) and not is_service_history_header(raw[i]) and not is_current_mileage_row(raw[i]):
                if any(c.strip() for c in raw[i]):
                    hist_rows.append(raw[i])
                else:
                    break
                i += 1
            records = parse_service_history(hist_rows, label)
            result["maintenance_records"].extend(records)
            continue

        i += 1

    return result


# ---------------------------------------------------------------------------
# Database write
# ---------------------------------------------------------------------------

def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_profiles (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL UNIQUE,
            make VARCHAR(100) DEFAULT '',
            model VARCHAR(100) DEFAULT '',
            year INTEGER,
            vin VARCHAR(17) DEFAULT '',
            license_plate VARCHAR(20) DEFAULT '',
            oil_type VARCHAR(50) DEFAULT '',
            oil_capacity_with_filter DECIMAL(5,2),
            oil_capacity_without_filter DECIMAL(5,2),
            transmission_fluid_type VARCHAR(50) DEFAULT '',
            transmission_fluid_capacity DECIMAL(5,2),
            coolant_type VARCHAR(50) DEFAULT '',
            current_mileage INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_fuel_records (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            date DATE NOT NULL,
            mileage INTEGER NOT NULL,
            miles_since_last DECIMAL(10,1),
            gallons DECIMAL(8,3),
            price_per_gallon DECIMAL(8,3),
            total_cost DECIMAL(10,2),
            mpg DECIMAL(6,2),
            tank_percent DECIMAL(5,1),
            is_full_fillup BOOLEAN DEFAULT TRUE,
            station VARCHAR(200) DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_maintenance_records (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            type_name VARCHAR(200) NOT NULL,
            date DATE NOT NULL,
            mileage INTEGER NOT NULL,
            cost DECIMAL(10,2),
            is_shop_performed BOOLEAN DEFAULT FALSE,
            shop_name VARCHAR(200) DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_inspection_items (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            name VARCHAR(200) NOT NULL,
            periodicity_days INTEGER NOT NULL DEFAULT 30,
            last_checked_date DATE,
            is_built_in BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def write_to_db(data: dict, tenant_id: int, dry_run: bool):
    if dry_run:
        print("\n--- DRY RUN (no DB writes) ---")
        print(f"  Fuel records:        {len(data['fuel_records'])}")
        print(f"  Maintenance records: {len(data['maintenance_records'])}")
        print(f"  Inspection items:    {len(data['inspection_items'])}")
        print(f"  Current mileage:     {data['current_mileage']}")
        print("\nFuel sample (first 3):")
        for r in data["fuel_records"][:3]:
            print(f"  {r}")
        print("\nMaintenance records:")
        for r in data["maintenance_records"]:
            print(f"  {r}")
        print("\nInspection items:")
        for r in data["inspection_items"]:
            print(f"  {r}")
        return

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            ensure_tables(cur)

            # Vehicle profile (upsert current mileage)
            if data["current_mileage"]:
                cur.execute("""
                    INSERT INTO vehicle_profiles (tenant_id, current_mileage)
                    VALUES (%s, %s)
                    ON CONFLICT (tenant_id) DO UPDATE SET
                        current_mileage = EXCLUDED.current_mileage,
                        updated_at = NOW()
                """, (tenant_id, data["current_mileage"]))
                print(f"  Profile: current_mileage set to {data['current_mileage']:,}")

            # Fuel records
            fuel_count = 0
            for r in data["fuel_records"]:
                cur.execute("""
                    INSERT INTO vehicle_fuel_records (
                        tenant_id, date, mileage, miles_since_last, gallons, mpg, is_full_fillup
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    tenant_id, r["date"], r["mileage"], r["miles_since_last"],
                    r["gallons"], r["mpg"], True,
                ))
                fuel_count += 1
            print(f"  Inserted {fuel_count} fuel records")

            # Maintenance records
            maint_count = 0
            for r in data["maintenance_records"]:
                cur.execute("""
                    INSERT INTO vehicle_maintenance_records (
                        tenant_id, type_name, date, mileage
                    ) VALUES (%s, %s, %s, %s)
                """, (tenant_id, r["type_name"], r["date"], r["mileage"]))
                maint_count += 1
            print(f"  Inserted {maint_count} maintenance records")

            # Inspection items (skip if any already exist for this tenant)
            existing = cur.execute(
                "SELECT COUNT(*) AS n FROM vehicle_inspection_items WHERE tenant_id = %s",
                (tenant_id,)
            ).fetchone()
            if existing and existing["n"] > 0:
                print(f"  Skipped inspection items (already {existing['n']} exist for tenant {tenant_id})")
            else:
                for item in data["inspection_items"]:
                    cur.execute("""
                        INSERT INTO vehicle_inspection_items (
                            tenant_id, name, periodicity_days, last_checked_date, is_built_in
                        ) VALUES (%s, %s, %s, %s, TRUE)
                    """, (tenant_id, item["name"], item["periodicity_days"], item["last_checked_date"]))
                print(f"  Inserted {len(data['inspection_items'])} inspection items")

        conn.commit()
    print("\nImport complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Import Maintenance.csv into Neon")
    parser.add_argument("csv_path", help="Path to Maintenance.csv")
    parser.add_argument("--tenant-id", type=int, default=1, help="Tenant ID (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't write to DB")
    args = parser.parse_args()

    if not os.path.exists(args.csv_path):
        print(f"File not found: {args.csv_path}")
        sys.exit(1)

    print(f"Parsing {args.csv_path}...")
    data = parse_csv(args.csv_path)
    write_to_db(data, args.tenant_id, args.dry_run)


if __name__ == "__main__":
    main()
