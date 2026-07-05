from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.tenancy import current_tenant_id
from db import query_db, with_db_cursor

router = APIRouter()

_tables_ready = False

# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

def ensure_vehicle_tables():
    global _tables_ready
    if _tables_ready:
        return
    with with_db_cursor() as (conn, cur):
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
            CREATE INDEX IF NOT EXISTS idx_vehicle_fuel_tenant_date
                ON vehicle_fuel_records(tenant_id, date DESC)
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
            CREATE INDEX IF NOT EXISTS idx_vehicle_maint_tenant_date
                ON vehicle_maintenance_records(tenant_id, date DESC)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_issues (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT DEFAULT '',
                severity VARCHAR(50) DEFAULT 'medium',
                mileage_noticed INTEGER,
                date_noticed DATE,
                is_resolved BOOLEAN DEFAULT FALSE,
                resolved_date DATE,
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
        cur.execute("ALTER TABLE vehicle_profiles ADD COLUMN IF NOT EXISTS tank_capacity_gallons DECIMAL(6,3)")
        cur.execute("ALTER TABLE vehicle_fuel_records ADD COLUMN IF NOT EXISTS linked_transaction_id TEXT")
        cur.execute("ALTER TABLE vehicle_fuel_records ADD COLUMN IF NOT EXISTS linked_merchant VARCHAR(300)")
        cur.execute("ALTER TABLE vehicle_maintenance_records ADD COLUMN IF NOT EXISTS linked_transaction_id TEXT")
        cur.execute("ALTER TABLE vehicle_maintenance_records ADD COLUMN IF NOT EXISTS linked_merchant VARCHAR(300)")
        # client_id lets the Android app queue these writes offline and retry
        # them idempotently once connectivity returns (see VehicleOfflineRepository.kt).
        # Nullable + partial unique index so pre-existing rows (created before
        # this column existed) aren't affected.
        cur.execute("ALTER TABLE vehicle_fuel_records ADD COLUMN IF NOT EXISTS client_id TEXT")
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicle_fuel_client_id
                ON vehicle_fuel_records(tenant_id, client_id) WHERE client_id IS NOT NULL
        """)
        cur.execute("ALTER TABLE vehicle_maintenance_records ADD COLUMN IF NOT EXISTS client_id TEXT")
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicle_maint_client_id
                ON vehicle_maintenance_records(tenant_id, client_id) WHERE client_id IS NOT NULL
        """)
        cur.execute("ALTER TABLE vehicle_issues ADD COLUMN IF NOT EXISTS client_id TEXT")
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicle_issues_client_id
                ON vehicle_issues(tenant_id, client_id) WHERE client_id IS NOT NULL
        """)
        cur.execute("ALTER TABLE vehicle_inspection_items ADD COLUMN IF NOT EXISTS client_id TEXT")
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicle_inspection_client_id
                ON vehicle_inspection_items(tenant_id, client_id) WHERE client_id IS NOT NULL
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS map_trips (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                ended_at TIMESTAMPTZ NOT NULL,
                origin_name TEXT DEFAULT '',
                destination_name TEXT DEFAULT '',
                distance_miles DECIMAL(10,3),
                duration_seconds INTEGER,
                transport_type VARCHAR(50) DEFAULT 'automobile',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_map_trips_tenant_date
                ON map_trips(tenant_id, started_at DESC)
        """)
        # Tires, corrective repairs, and DIY procedures were local-only on both
        # platforms (see VehicleStore.swift / the old DataStore-only
        # VehicleLocalStore.kt) — these tables give them real backend sync too.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_tire_sets (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                brand TEXT DEFAULT '',
                model TEXT DEFAULT '',
                size TEXT DEFAULT '',
                install_date DATE,
                install_mileage INTEGER DEFAULT 0,
                required_pressure_front INTEGER DEFAULT 35,
                required_pressure_rear INTEGER DEFAULT 35,
                pressure_checks JSONB NOT NULL DEFAULT '[]',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_corrective_records (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                date DATE NOT NULL,
                mileage INTEGER DEFAULT 0,
                description TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                parts_replaced JSONB NOT NULL DEFAULT '[]',
                cost DECIMAL(10,2),
                resolved_issue BOOLEAN DEFAULT FALSE,
                linked_issue_id INTEGER,
                notes TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_procedures (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                title TEXT NOT NULL,
                related_type_name TEXT DEFAULT '',
                tools JSONB NOT NULL DEFAULT '[]',
                parts JSONB NOT NULL DEFAULT '[]',
                steps JSONB NOT NULL DEFAULT '[]',
                notes TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, client_id)
            )
        """)
        conn.commit()
    _tables_ready = True


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class VehicleProfileIn(BaseModel):
    make: Optional[str] = ""
    model: Optional[str] = ""
    year: Optional[int] = None
    vin: Optional[str] = ""
    license_plate: Optional[str] = ""
    oil_type: Optional[str] = ""
    oil_capacity_with_filter: Optional[float] = None
    oil_capacity_without_filter: Optional[float] = None
    transmission_fluid_type: Optional[str] = ""
    transmission_fluid_capacity: Optional[float] = None
    coolant_type: Optional[str] = ""
    current_mileage: Optional[int] = 0
    tank_capacity_gallons: Optional[float] = None
    notes: Optional[str] = ""

class FuelRecordIn(BaseModel):
    client_id: Optional[str] = None
    date: date
    mileage: int
    miles_since_last: Optional[float] = None
    gallons: Optional[float] = None
    price_per_gallon: Optional[float] = None
    total_cost: Optional[float] = None
    mpg: Optional[float] = None
    tank_percent: Optional[float] = None
    is_full_fillup: bool = True
    station: Optional[str] = ""
    notes: Optional[str] = ""

class FuelRecordBulkIn(BaseModel):
    records: List[FuelRecordIn]

class MaintenanceRecordIn(BaseModel):
    client_id: Optional[str] = None
    type_name: str
    date: date
    mileage: int
    cost: Optional[float] = None
    is_shop_performed: bool = False
    shop_name: Optional[str] = ""
    notes: Optional[str] = ""

class MaintenanceBulkIn(BaseModel):
    records: List[MaintenanceRecordIn]

class IssueIn(BaseModel):
    client_id: Optional[str] = None
    title: str
    description: Optional[str] = ""
    severity: Optional[str] = "medium"
    mileage_noticed: Optional[int] = None
    date_noticed: Optional[date] = None
    is_resolved: bool = False
    resolved_date: Optional[date] = None
    notes: Optional[str] = ""

class IssueResolveIn(BaseModel):
    resolved_date: Optional[date] = None

class InspectionItemIn(BaseModel):
    client_id: Optional[str] = None
    name: str
    periodicity_days: int = 30
    last_checked_date: Optional[date] = None
    is_built_in: bool = False

class TripIn(BaseModel):
    started_at: datetime
    ended_at: datetime
    origin_name: Optional[str] = ""
    destination_name: Optional[str] = ""
    distance_miles: Optional[float] = None
    duration_seconds: Optional[int] = None
    transport_type: Optional[str] = "automobile"

class MileageUpdateIn(BaseModel):
    current_mileage: int


class TireSetIn(BaseModel):
    client_id: str
    brand: Optional[str] = ""
    model: Optional[str] = ""
    size: Optional[str] = ""
    install_date: Optional[date] = None
    install_mileage: int = 0
    required_pressure_front: int = 35
    required_pressure_rear: int = 35
    pressure_checks: List[dict] = []
    is_active: bool = True


class CorrectiveRecordIn(BaseModel):
    client_id: str
    date: date
    mileage: int = 0
    description: Optional[str] = ""
    reason: Optional[str] = ""
    parts_replaced: List[str] = []
    cost: Optional[float] = None
    resolved_issue: bool = False
    linked_issue_id: Optional[int] = None
    notes: Optional[str] = ""


class VehicleProcedureIn(BaseModel):
    client_id: str
    title: str
    related_type_name: Optional[str] = ""
    tools: List[str] = []
    parts: List[str] = []
    steps: List[dict] = []
    notes: Optional[str] = ""


# ---------------------------------------------------------------------------
# Vehicle profile
# ---------------------------------------------------------------------------

@router.get("/vehicle/profile")
def get_vehicle_profile():
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db("SELECT * FROM vehicle_profiles WHERE tenant_id = %s LIMIT 1", (tid,))
    if not rows:
        return {}
    return _serialize(rows[0])


@router.put("/vehicle/profile")
def upsert_vehicle_profile(body: VehicleProfileIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO vehicle_profiles (
                tenant_id, make, model, year, vin, license_plate,
                oil_type, oil_capacity_with_filter, oil_capacity_without_filter,
                transmission_fluid_type, transmission_fluid_capacity,
                coolant_type, current_mileage, tank_capacity_gallons, notes, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT (tenant_id) DO UPDATE SET
                make = EXCLUDED.make,
                model = EXCLUDED.model,
                year = EXCLUDED.year,
                vin = EXCLUDED.vin,
                license_plate = EXCLUDED.license_plate,
                oil_type = EXCLUDED.oil_type,
                oil_capacity_with_filter = EXCLUDED.oil_capacity_with_filter,
                oil_capacity_without_filter = EXCLUDED.oil_capacity_without_filter,
                transmission_fluid_type = EXCLUDED.transmission_fluid_type,
                transmission_fluid_capacity = EXCLUDED.transmission_fluid_capacity,
                coolant_type = EXCLUDED.coolant_type,
                current_mileage = EXCLUDED.current_mileage,
                tank_capacity_gallons = EXCLUDED.tank_capacity_gallons,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            RETURNING *
        """, (
            tid, body.make, body.model, body.year, body.vin, body.license_plate,
            body.oil_type, body.oil_capacity_with_filter, body.oil_capacity_without_filter,
            body.transmission_fluid_type, body.transmission_fluid_capacity,
            body.coolant_type, body.current_mileage, body.tank_capacity_gallons, body.notes,
        ))
        return _serialize(cur.fetchone())


# ---------------------------------------------------------------------------
# Fuel records
# ---------------------------------------------------------------------------

@router.get("/vehicle/fuel")
def list_fuel_records(limit: int = 200, offset: int = 0):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db("""
        SELECT * FROM vehicle_fuel_records
        WHERE tenant_id = %s
        ORDER BY date DESC, mileage DESC
        LIMIT %s OFFSET %s
    """, (tid, limit, offset))
    total = query_db("SELECT COUNT(*) AS n FROM vehicle_fuel_records WHERE tenant_id = %s", (tid,))
    return {"records": [_serialize(r) for r in rows], "total": total[0]["n"]}


@router.post("/vehicle/fuel")
def add_fuel_record(body: FuelRecordIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO vehicle_fuel_records (
                tenant_id, client_id, date, mileage, miles_since_last, gallons,
                price_per_gallon, total_cost, mpg, tank_percent,
                is_full_fillup, station, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) WHERE client_id IS NOT NULL DO UPDATE SET
                date = EXCLUDED.date,
                mileage = EXCLUDED.mileage,
                miles_since_last = EXCLUDED.miles_since_last,
                gallons = EXCLUDED.gallons,
                price_per_gallon = EXCLUDED.price_per_gallon,
                total_cost = EXCLUDED.total_cost,
                mpg = EXCLUDED.mpg,
                tank_percent = EXCLUDED.tank_percent,
                is_full_fillup = EXCLUDED.is_full_fillup,
                station = EXCLUDED.station,
                notes = EXCLUDED.notes
            RETURNING *
        """, (
            tid, body.client_id, body.date, body.mileage, body.miles_since_last, body.gallons,
            body.price_per_gallon, body.total_cost, body.mpg, body.tank_percent,
            body.is_full_fillup, body.station, body.notes,
        ))
        return _serialize(cur.fetchone())


@router.post("/vehicle/fuel/bulk")
def bulk_import_fuel(body: FuelRecordBulkIn):
    """Import many fuel records at once (used for historical CSV import)."""
    ensure_vehicle_tables()
    tid = current_tenant_id()
    inserted = 0
    with with_db_cursor() as (conn, cur):
        for r in body.records:
            cur.execute("""
                INSERT INTO vehicle_fuel_records (
                    tenant_id, date, mileage, miles_since_last, gallons,
                    price_per_gallon, total_cost, mpg, tank_percent,
                    is_full_fillup, station, notes
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (
                tid, r.date, r.mileage, r.miles_since_last, r.gallons,
                r.price_per_gallon, r.total_cost, r.mpg, r.tank_percent,
                r.is_full_fillup, r.station, r.notes,
            ))
            inserted += cur.rowcount
    return {"inserted": inserted, "submitted": len(body.records)}


@router.delete("/vehicle/fuel/{record_id}")
def delete_fuel_record(record_id: int):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM vehicle_fuel_records WHERE id = %s AND tenant_id = %s",
            (record_id, tid)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Fuel analytics
# ---------------------------------------------------------------------------

@router.get("/vehicle/fuel/stats")
def fuel_stats():
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db("""
        SELECT
            COUNT(*) AS total_fillups,
            SUM(gallons) AS total_gallons,
            SUM(total_cost) AS total_spent,
            AVG(mpg) FILTER (WHERE mpg > 0 AND mpg < 100) AS avg_mpg,
            MAX(mileage) AS latest_mileage,
            MIN(date) AS first_date,
            MAX(date) AS last_date
        FROM vehicle_fuel_records
        WHERE tenant_id = %s
    """, (tid,))
    return _serialize(rows[0]) if rows else {}


# ---------------------------------------------------------------------------
# Maintenance records
# ---------------------------------------------------------------------------

@router.get("/vehicle/maintenance")
def list_maintenance(limit: int = 200, offset: int = 0):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db("""
        SELECT * FROM vehicle_maintenance_records
        WHERE tenant_id = %s
        ORDER BY date DESC, mileage DESC
        LIMIT %s OFFSET %s
    """, (tid, limit, offset))
    total = query_db(
        "SELECT COUNT(*) AS n FROM vehicle_maintenance_records WHERE tenant_id = %s", (tid,)
    )
    return {"records": [_serialize(r) for r in rows], "total": total[0]["n"]}


@router.post("/vehicle/maintenance")
def add_maintenance(body: MaintenanceRecordIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO vehicle_maintenance_records (
                tenant_id, client_id, type_name, date, mileage, cost,
                is_shop_performed, shop_name, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) WHERE client_id IS NOT NULL DO UPDATE SET
                type_name = EXCLUDED.type_name,
                date = EXCLUDED.date,
                mileage = EXCLUDED.mileage,
                cost = EXCLUDED.cost,
                is_shop_performed = EXCLUDED.is_shop_performed,
                shop_name = EXCLUDED.shop_name,
                notes = EXCLUDED.notes
            RETURNING *
        """, (
            tid, body.client_id, body.type_name, body.date, body.mileage, body.cost,
            body.is_shop_performed, body.shop_name, body.notes,
        ))
        return _serialize(cur.fetchone())


@router.post("/vehicle/maintenance/bulk")
def bulk_import_maintenance(body: MaintenanceBulkIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    inserted = 0
    with with_db_cursor() as (conn, cur):
        for r in body.records:
            cur.execute("""
                INSERT INTO vehicle_maintenance_records (
                    tenant_id, type_name, date, mileage, cost,
                    is_shop_performed, shop_name, notes
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                tid, r.type_name, r.date, r.mileage, r.cost,
                r.is_shop_performed, r.shop_name, r.notes,
            ))
            inserted += cur.rowcount
    return {"inserted": inserted}


@router.delete("/vehicle/maintenance/{record_id}")
def delete_maintenance(record_id: int):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM vehicle_maintenance_records WHERE id = %s AND tenant_id = %s",
            (record_id, tid)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

@router.get("/vehicle/issues")
def list_issues():
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db("""
        SELECT * FROM vehicle_issues
        WHERE tenant_id = %s
        ORDER BY is_resolved ASC, date_noticed DESC NULLS LAST
    """, (tid,))
    return [_serialize(r) for r in rows]


@router.post("/vehicle/issues")
def add_issue(body: IssueIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO vehicle_issues (
                tenant_id, client_id, title, description, severity,
                mileage_noticed, date_noticed, is_resolved, resolved_date, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) WHERE client_id IS NOT NULL DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                severity = EXCLUDED.severity,
                mileage_noticed = EXCLUDED.mileage_noticed,
                date_noticed = EXCLUDED.date_noticed,
                is_resolved = EXCLUDED.is_resolved,
                resolved_date = EXCLUDED.resolved_date,
                notes = EXCLUDED.notes
            RETURNING *
        """, (
            tid, body.client_id, body.title, body.description, body.severity,
            body.mileage_noticed, body.date_noticed, body.is_resolved, body.resolved_date, body.notes,
        ))
        return _serialize(cur.fetchone())


@router.post("/vehicle/issues/{issue_id}/resolve")
def resolve_issue(issue_id: int, body: IssueResolveIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    resolved_date = body.resolved_date or date.today()
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            UPDATE vehicle_issues
            SET is_resolved = TRUE, resolved_date = %s
            WHERE id = %s AND tenant_id = %s
            RETURNING *
        """, (resolved_date, issue_id, tid))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Issue not found")
        return _serialize(cur.fetchone())


@router.delete("/vehicle/issues/{issue_id}")
def delete_issue(issue_id: int):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM vehicle_issues WHERE id = %s AND tenant_id = %s",
            (issue_id, tid)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Issue not found")
    return {"deleted": issue_id}


# ---------------------------------------------------------------------------
# Inspection items
# ---------------------------------------------------------------------------

@router.get("/vehicle/inspections")
def list_inspections():
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM vehicle_inspection_items WHERE tenant_id = %s ORDER BY name",
        (tid,)
    )
    return [_serialize(r) for r in rows]


@router.post("/vehicle/inspections")
def add_inspection(body: InspectionItemIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO vehicle_inspection_items (
                tenant_id, client_id, name, periodicity_days, last_checked_date, is_built_in
            ) VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) WHERE client_id IS NOT NULL DO UPDATE SET
                name = EXCLUDED.name,
                periodicity_days = EXCLUDED.periodicity_days,
                last_checked_date = EXCLUDED.last_checked_date,
                is_built_in = EXCLUDED.is_built_in
            RETURNING *
        """, (tid, body.client_id, body.name, body.periodicity_days, body.last_checked_date, body.is_built_in))
        return _serialize(cur.fetchone())


@router.post("/vehicle/inspections/{item_id}/check")
def mark_inspected(item_id: int, checked_date: Optional[date] = None):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    d = checked_date or date.today()
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            UPDATE vehicle_inspection_items
            SET last_checked_date = %s
            WHERE id = %s AND tenant_id = %s
            RETURNING *
        """, (d, item_id, tid))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
        return _serialize(cur.fetchone())


@router.delete("/vehicle/inspections/{item_id}")
def delete_inspection(item_id: int):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM vehicle_inspection_items WHERE id = %s AND tenant_id = %s",
            (item_id, tid)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
    return {"deleted": item_id}


# ---------------------------------------------------------------------------
# Tire sets
# ---------------------------------------------------------------------------

@router.get("/vehicle/tires")
def list_tire_sets():
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM vehicle_tire_sets WHERE tenant_id = %s ORDER BY created_at DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/vehicle/tires")
def upsert_tire_set(body: TireSetIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO vehicle_tire_sets (
                tenant_id, client_id, brand, model, size, install_date, install_mileage,
                required_pressure_front, required_pressure_rear, pressure_checks, is_active
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                brand = EXCLUDED.brand,
                model = EXCLUDED.model,
                size = EXCLUDED.size,
                install_date = EXCLUDED.install_date,
                install_mileage = EXCLUDED.install_mileage,
                required_pressure_front = EXCLUDED.required_pressure_front,
                required_pressure_rear = EXCLUDED.required_pressure_rear,
                pressure_checks = EXCLUDED.pressure_checks,
                is_active = EXCLUDED.is_active
            RETURNING *
            """,
            (
                tid, body.client_id, body.brand, body.model, body.size, body.install_date, body.install_mileage,
                body.required_pressure_front, body.required_pressure_rear, json.dumps(body.pressure_checks), body.is_active,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/vehicle/tires/{record_id}")
def delete_tire_set(record_id: int):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM vehicle_tire_sets WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Corrective records (repairs)
# ---------------------------------------------------------------------------

@router.get("/vehicle/corrective")
def list_corrective_records():
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM vehicle_corrective_records WHERE tenant_id = %s ORDER BY date DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/vehicle/corrective")
def upsert_corrective_record(body: CorrectiveRecordIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO vehicle_corrective_records (
                tenant_id, client_id, date, mileage, description, reason,
                parts_replaced, cost, resolved_issue, linked_issue_id, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                date = EXCLUDED.date,
                mileage = EXCLUDED.mileage,
                description = EXCLUDED.description,
                reason = EXCLUDED.reason,
                parts_replaced = EXCLUDED.parts_replaced,
                cost = EXCLUDED.cost,
                resolved_issue = EXCLUDED.resolved_issue,
                linked_issue_id = EXCLUDED.linked_issue_id,
                notes = EXCLUDED.notes
            RETURNING *
            """,
            (
                tid, body.client_id, body.date, body.mileage, body.description, body.reason,
                json.dumps(body.parts_replaced), body.cost, body.resolved_issue, body.linked_issue_id, body.notes,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/vehicle/corrective/{record_id}")
def delete_corrective_record(record_id: int):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM vehicle_corrective_records WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# DIY procedures
# ---------------------------------------------------------------------------

@router.get("/vehicle/procedures")
def list_procedures():
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db(
        "SELECT * FROM vehicle_procedures WHERE tenant_id = %s ORDER BY updated_at DESC",
        (tid,),
    )
    return [_serialize(r) for r in rows]


@router.post("/vehicle/procedures")
def upsert_procedure(body: VehicleProcedureIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            """
            INSERT INTO vehicle_procedures (
                tenant_id, client_id, title, related_type_name, tools, parts, steps, notes, updated_at
            ) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,NOW())
            ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                title = EXCLUDED.title,
                related_type_name = EXCLUDED.related_type_name,
                tools = EXCLUDED.tools,
                parts = EXCLUDED.parts,
                steps = EXCLUDED.steps,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            RETURNING *
            """,
            (
                tid, body.client_id, body.title, body.related_type_name,
                json.dumps(body.tools), json.dumps(body.parts), json.dumps(body.steps), body.notes,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return _serialize(row)


@router.delete("/vehicle/procedures/{record_id}")
def delete_procedure(record_id: int):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute(
            "DELETE FROM vehicle_procedures WHERE id = %s AND tenant_id = %s",
            (record_id, tid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        conn.commit()
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Map trips
# ---------------------------------------------------------------------------

@router.post("/vehicle/trips")
def log_trip(body: TripIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO map_trips (
                tenant_id, started_at, ended_at, origin_name, destination_name,
                distance_miles, duration_seconds, transport_type
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
        """, (
            tid, body.started_at, body.ended_at, body.origin_name, body.destination_name,
            body.distance_miles, body.duration_seconds, body.transport_type,
        ))
        return _serialize(cur.fetchone())


@router.get("/vehicle/trips")
def list_trips(limit: int = 100, offset: int = 0):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db("""
        SELECT * FROM map_trips WHERE tenant_id = %s
        ORDER BY started_at DESC LIMIT %s OFFSET %s
    """, (tid, limit, offset))
    total = query_db("SELECT COUNT(*) AS n FROM map_trips WHERE tenant_id = %s", (tid,))
    return {"trips": [_serialize(r) for r in rows], "total": total[0]["n"]}


@router.get("/vehicle/trips/stats")
def trip_stats():
    ensure_vehicle_tables()
    tid = current_tenant_id()
    rows = query_db("""
        SELECT
            COUNT(*) AS total_trips,
            COALESCE(SUM(distance_miles), 0) AS total_miles,
            COALESCE(AVG(distance_miles), 0) AS avg_miles,
            COALESCE(SUM(CASE WHEN started_at >= NOW() - INTERVAL '7 days' THEN distance_miles ELSE 0 END), 0) AS miles_this_week,
            COALESCE(SUM(CASE WHEN started_at >= DATE_TRUNC('month', NOW()) THEN distance_miles ELSE 0 END), 0) AS miles_this_month,
            COALESCE(COUNT(CASE WHEN started_at >= DATE_TRUNC('month', NOW()) THEN 1 END), 0) AS trips_this_month
        FROM map_trips WHERE tenant_id = %s
    """, (tid,))
    return _serialize(rows[0]) if rows else {}


@router.patch("/vehicle/profile/mileage")
def update_mileage(body: MileageUpdateIn):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO vehicle_profiles (tenant_id, current_mileage, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (tenant_id) DO UPDATE SET
                current_mileage = EXCLUDED.current_mileage,
                updated_at = NOW()
            RETURNING current_mileage
        """, (tid, body.current_mileage))
        conn.commit()
        row = cur.fetchone()
    return {"current_mileage": row["current_mileage"]}


# ---------------------------------------------------------------------------
# Transaction pairing
# ---------------------------------------------------------------------------

class LinkTransactionBody(BaseModel):
    kind: str  # "fuel" or "maintenance"
    record_id: int
    transaction_id: str
    merchant: Optional[str] = None


@router.get("/vehicle/match-transactions")
def match_transactions(kind: str, record_id: int):
    """Return candidate transactions within 7 days after the vehicle record date."""
    ensure_vehicle_tables()
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")

    table = "vehicle_fuel_records" if kind == "fuel" else "vehicle_maintenance_records"
    amount_col = "total_cost" if kind == "fuel" else "cost"
    rows = query_db(
        f"SELECT date, {amount_col} AS amount FROM {table} WHERE id = %s AND tenant_id = %s LIMIT 1",
        (record_id, int(tid)),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="record_not_found")

    rec_date = rows[0].get("date")
    rec_amount = float(rows[0].get("amount") or 0)

    import logging as _log
    _log.getLogger("vehicle").warning("match_transactions: kind=%s record_id=%s date=%s amount=%s tid=%s", kind, record_id, rec_date, rec_amount, tid)

    # Fetch candidate transactions in [rec_date, rec_date + 7 days]
    candidates = query_db(
        """
        WITH base AS (
            SELECT
                t.id,
                COALESCE(NULLIF(TRIM(t.postedDate),'unknown'), NULLIF(TRIM(t.purchaseDate),'unknown')) AS raw_date,
                t.amount::double precision AS amount,
                t.merchant,
                TRIM(t.category) AS category
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE t.tenant_id = %s AND a.tenant_id = %s AND COALESCE(t.is_ignored, false) = false
        ),
        norm AS (
            SELECT *,
                CASE
                    WHEN raw_date IS NULL THEN NULL
                    WHEN length(raw_date)=8  THEN to_date(raw_date, 'MM/DD/YY')
                    WHEN length(raw_date)=10 THEN to_date(raw_date, 'MM/DD/YYYY')
                    ELSE NULL
                END AS d
            FROM base
        )
        SELECT id, d::text AS date, amount, merchant, LOWER(TRIM(COALESCE(category, ''))) AS category
        FROM norm
        WHERE d IS NOT NULL
          AND d BETWEEN %s AND (%s + INTERVAL '7 days')
          AND amount > 0
          AND (
            LOWER(TRIM(COALESCE(category, ''))) = ''
            OR LOWER(TRIM(COALESCE(category, ''))) LIKE '%%gas%%'
            OR LOWER(TRIM(COALESCE(category, ''))) LIKE '%%fuel%%'
            OR LOWER(TRIM(COALESCE(category, ''))) LIKE '%%auto%%'
            OR LOWER(TRIM(COALESCE(category, ''))) LIKE '%%vehicle%%'
            OR LOWER(TRIM(COALESCE(category, ''))) LIKE '%%service station%%'
            OR LOWER(TRIM(COALESCE(category, ''))) LIKE '%%unknown%%'
          )
        ORDER BY ABS(amount - %s) ASC, d ASC
        LIMIT 30
        """,
        (int(tid), int(tid), rec_date, rec_date, rec_amount),
    )

    _log.getLogger("vehicle").warning("match_transactions: found %d candidates", len(candidates or []))
    return {"candidates": [_serialize(dict(r)) for r in (candidates or [])]}


@router.get("/vehicle/linked-transactions")
def linked_transactions():
    """Return all vehicle records that have a linked transaction."""
    ensure_vehicle_tables()
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")

    fuel = query_db(
        "SELECT id, date, total_cost AS amount, linked_transaction_id, linked_merchant FROM vehicle_fuel_records WHERE tenant_id = %s AND linked_transaction_id IS NOT NULL ORDER BY date DESC",
        (int(tid),),
    )
    maint = query_db(
        "SELECT id, date, cost AS amount, linked_transaction_id, linked_merchant, type_name FROM vehicle_maintenance_records WHERE tenant_id = %s AND linked_transaction_id IS NOT NULL ORDER BY date DESC",
        (int(tid),),
    )
    return {
        "fuel": [_serialize(dict(r)) for r in (fuel or [])],
        "maintenance": [_serialize(dict(r)) for r in (maint or [])],
    }


@router.post("/vehicle/link-transaction")
def link_transaction(body: LinkTransactionBody):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")

    table = "vehicle_fuel_records" if body.kind == "fuel" else "vehicle_maintenance_records"
    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"UPDATE {table} SET linked_transaction_id = %s, linked_merchant = %s WHERE id = %s AND tenant_id = %s",
            (body.transaction_id, (body.merchant or "")[:300], body.record_id, int(tid)),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="record_not_found")
        conn.commit()
    return {"ok": True}


@router.delete("/vehicle/link-transaction")
def unlink_transaction(kind: str, record_id: int):
    ensure_vehicle_tables()
    tid = current_tenant_id()
    if not tid:
        raise HTTPException(status_code=403, detail="tenant_required")

    table = "vehicle_fuel_records" if kind == "fuel" else "vehicle_maintenance_records"
    with with_db_cursor() as (conn, cur):
        cur.execute(
            f"UPDATE {table} SET linked_transaction_id = NULL, linked_merchant = NULL WHERE id = %s AND tenant_id = %s",
            (record_id, int(tid)),
        )
        conn.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JSONB_LIST_COLUMNS = {"pressure_checks", "parts_replaced", "tools", "parts", "steps"}


def _serialize(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            # Plain int columns (id, tenant_id, year, current_mileage, ...) also have
            # __float__, so a hasattr(v, "__float__") check here would wrongly turn
            # them into JSON floats (e.g. "id": 1.0) that strict clients can't parse
            # back into an Int field. Only actual NUMERIC/DECIMAL columns need this.
            out[k] = float(v)
        elif k in _JSONB_LIST_COLUMNS and isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = []
        else:
            out[k] = v
    return out
