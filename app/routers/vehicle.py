from __future__ import annotations

from datetime import date, datetime
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
    notes: Optional[str] = ""

class FuelRecordIn(BaseModel):
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
    title: str
    description: Optional[str] = ""
    severity: Optional[str] = "medium"
    mileage_noticed: Optional[int] = None
    date_noticed: Optional[date] = None
    notes: Optional[str] = ""

class IssueResolveIn(BaseModel):
    resolved_date: Optional[date] = None

class InspectionItemIn(BaseModel):
    name: str
    periodicity_days: int = 30
    last_checked_date: Optional[date] = None
    is_built_in: bool = False


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
                coolant_type, current_mileage, notes, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
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
                notes = EXCLUDED.notes,
                updated_at = NOW()
            RETURNING *
        """, (
            tid, body.make, body.model, body.year, body.vin, body.license_plate,
            body.oil_type, body.oil_capacity_with_filter, body.oil_capacity_without_filter,
            body.transmission_fluid_type, body.transmission_fluid_capacity,
            body.coolant_type, body.current_mileage, body.notes,
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
                tenant_id, date, mileage, miles_since_last, gallons,
                price_per_gallon, total_cost, mpg, tank_percent,
                is_full_fillup, station, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
        """, (
            tid, body.date, body.mileage, body.miles_since_last, body.gallons,
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
                tenant_id, type_name, date, mileage, cost,
                is_shop_performed, shop_name, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
        """, (
            tid, body.type_name, body.date, body.mileage, body.cost,
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
                tenant_id, title, description, severity,
                mileage_noticed, date_noticed, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
        """, (
            tid, body.title, body.description, body.severity,
            body.mileage_noticed, body.date_noticed, body.notes,
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
                tenant_id, name, periodicity_days, last_checked_date, is_built_in
            ) VALUES (%s,%s,%s,%s,%s)
            RETURNING *
        """, (tid, body.name, body.periodicity_days, body.last_checked_date, body.is_built_in))
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
# Helpers
# ---------------------------------------------------------------------------

def _serialize(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        elif hasattr(v, "__float__"):
            out[k] = float(v)
        else:
            out[k] = v
    return out
