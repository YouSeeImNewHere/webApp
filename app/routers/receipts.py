from __future__ import annotations

import datetime as dt
import json
import os
import re
import uuid
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.core.tenancy import current_tenant_id
from db import with_db_cursor


router = APIRouter(tags=["receipts"])


@lru_cache(maxsize=1)
def _get_cv2():
    # Lazy-load OpenCV so the web process can stay lean at idle.
    import cv2  # type: ignore

    return cv2


@lru_cache(maxsize=1)
def _get_receipt_ocr_runner():
    # Lazy-load OCR pipeline (pulls cv2/numpy/tesseract and optional paddle deps).
    from Receipts.receipts import run_receipt_ocr

    return run_receipt_ocr


@lru_cache(maxsize=1)
def _get_receipts_data_dir() -> str:
    from Receipts.receipts import DATA_DIR

    return str(DATA_DIR)


def _table_columns(cur, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = %s
        """,
        (table_name,),
    )
    return {str((r or {}).get("column_name") or "").strip().lower() for r in (cur.fetchall() or [])}


def _safe_json_loads(v: Any, fallback: Any):
    try:
        return json.loads(v) if isinstance(v, str) and v.strip() else fallback
    except Exception:
        return fallback


def _extract_parsed_from_row(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed = _safe_json_loads(row.get("parsed_json"), {}) or {}
    ocr = _safe_json_loads(row.get("ocr_json"), {}) or {}
    if not parsed and isinstance(ocr, dict):
        maybe = ocr.get("parsed")
        if isinstance(maybe, dict):
            parsed = maybe
    return parsed, (ocr if isinstance(ocr, dict) else {})


def _receipt_image_path_from_row(row: dict[str, Any]) -> str:
    return str(row.get("file_path") or row.get("image_path") or "").strip()


def _coerce_iso_from_mmddyy(raw: str | None) -> str | None:
    s = str(raw or "").strip()
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    m = re.match(r"^(\d{2})/(\d{2})/(\d{2})$", s)
    if not m:
        return None
    yy = int(m.group(3))
    yyyy = 2000 + yy if yy <= 69 else 1900 + yy
    return f"{yyyy:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"


def _parse_receipt_mmddyy(raw: str | None) -> dt.date | None:
    s = str(raw or "").strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{2})$", s)
    if not m:
        return None
    yy = int(m.group(3))
    yyyy = 2000 + yy if yy <= 69 else 1900 + yy
    try:
        return dt.date(yyyy, int(m.group(1)), int(m.group(2)))
    except Exception:
        return None


def _parse_tx_date(raw: str | None) -> dt.date | None:
    s = str(raw or "").strip()
    if not s or s.lower() == "unknown":
        return None
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def _merchant_tokens(s: str) -> set[str]:
    txt = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())
    stop = {"inc", "llc", "store", "market", "mart", "shop", "the", "co", "corp"}
    return {t for t in txt.split() if t and len(t) >= 2 and t not in stop}


def _merchant_overlap_score(a: str, b: str) -> float:
    A = _merchant_tokens(a)
    B = _merchant_tokens(b)
    if not A or not B:
        return 0.0
    inter = len(A & B)
    if inter <= 0:
        return 0.0
    return min(20.0, 20.0 * (inter / max(len(A), len(B))))


def _tenant_where(colset: set[str], tid: int | None, entity_alias: str = "") -> tuple[str, list[Any]]:
    pfx = f"{entity_alias}." if entity_alias else ""
    if "tenant_id" in colset and tid:
        return f"{pfx}tenant_id = %s", [int(tid)]
    return "TRUE", []


@router.post("/receipts/upload")
async def upload_receipt(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")

    receipt_id = str(uuid.uuid4())
    receipt_dir = os.path.join(_get_receipts_data_dir(), receipt_id)
    os.makedirs(receipt_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".jpg"

    orig_path = os.path.join(receipt_dir, f"orig{ext}")
    with open(orig_path, "wb") as f:
        f.write(await file.read())

    norm_path = os.path.join(receipt_dir, "orig.jpg")
    cv2 = _get_cv2()
    img = cv2.imread(orig_path)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image")
    cv2.imwrite(norm_path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])

    ocr = _get_receipt_ocr_runner()(receipt_id, norm_path)
    parsed = (ocr.get("parsed") if isinstance(ocr.get("parsed"), dict) else {}) or {}

    with open(os.path.join(receipt_dir, "ocr.json"), "w", encoding="utf-8") as f:
        json.dump(ocr, f, ensure_ascii=False, indent=2)

    tid = current_tenant_id()
    merchant_name = parsed.get("merchant") or None
    total = parsed.get("total")
    purchase_iso = _coerce_iso_from_mmddyy(parsed.get("purchase_date_mmddyy") or parsed.get("purchase_date"))
    confidence = None
    try:
        confidence = float((ocr.get("winner") or {}).get("score"))  # old payloads may omit winner
    except Exception:
        confidence = None

    with with_db_cursor() as (conn, cur):
        cols = _table_columns(cur, "receipts")
        if not cols:
            raise HTTPException(status_code=500, detail="receipts table missing")

        values: dict[str, Any] = {"id": receipt_id}
        if "created_at" in cols:
            values["created_at"] = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        if "original_filename" in cols:
            values["original_filename"] = file.filename or ""
        if "file_path" in cols:
            values["file_path"] = norm_path
        elif "image_path" in cols:
            values["image_path"] = norm_path
        if "mime_type" in cols:
            values["mime_type"] = file.content_type or "image/jpeg"
        if "parse_status" in cols:
            values["parse_status"] = "parsed"
        if "parsed_json" in cols:
            values["parsed_json"] = json.dumps(parsed, ensure_ascii=False)
        if "ocr_json" in cols:
            values["ocr_json"] = json.dumps(ocr, ensure_ascii=False)
        if "merchant_name" in cols:
            values["merchant_name"] = merchant_name
        if "purchase_date" in cols:
            values["purchase_date"] = purchase_iso
        if "total" in cols:
            values["total"] = total
        if "confidence" in cols:
            values["confidence"] = confidence
        if "tenant_id" in cols:
            values["tenant_id"] = int(tid) if tid else None

        ins_cols = list(values.keys())
        placeholders = ", ".join(["%s"] * len(ins_cols))
        cur.execute(
            f"INSERT INTO receipts ({', '.join(ins_cols)}) VALUES ({placeholders})",
            tuple(values[c] for c in ins_cols),
        )
        conn.commit()

    return JSONResponse(
        {
            "receipt_id": receipt_id,
            "image_url": f"/receipts/{receipt_id}/image",
            "debug_dir": f"/receipts/{receipt_id}/debug",
            "ocr": ocr,
            "parsed": parsed,
        }
    )


@router.get("/receipts")
def list_receipts(q: str = "", limit: int = 100, offset: int = 0):
    tid = current_tenant_id()
    with with_db_cursor() as (_, cur):
        cols = _table_columns(cur, "receipts")
        if not cols:
            return {"ok": True, "receipts": []}

        select_cols = [
            c
            for c in [
                "id",
                "created_at",
                "original_filename",
                "file_path",
                "image_path",
                "mime_type",
                "parse_status",
                "parsed_json",
                "ocr_json",
                "merchant_name",
                "purchase_date",
                "total",
                "confidence",
                "tenant_id",
            ]
            if c in cols
        ]

        where_parts: list[str] = []
        params: list[Any] = []
        tenant_where, tenant_params = _tenant_where(cols, tid)
        where_parts.append(tenant_where)
        params.extend(tenant_params)

        q_norm = (q or "").strip().lower()
        if q_norm:
            like = f"%{q_norm}%"
            ors = []
            for c in ("merchant_name", "original_filename", "file_path", "image_path"):
                if c in cols:
                    ors.append(f"LOWER(COALESCE({c}, '')) LIKE %s")
                    params.append(like)
            if ors:
                where_parts.append("(" + " OR ".join(ors) + ")")

        order_col = "created_at" if "created_at" in cols else "id"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        cur.execute(
            f"""
            SELECT {", ".join(select_cols)}
            FROM receipts
            WHERE {" AND ".join(where_parts)}
            ORDER BY {order_col} DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params),
        )
        rows = cur.fetchall() or []

    receipts: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        parsed, ocr = _extract_parsed_from_row(d)
        d["parsed_json"] = parsed
        if not d.get("original_filename"):
            p = _receipt_image_path_from_row(d)
            d["original_filename"] = os.path.basename(p) if p else ""
        if not d.get("merchant_name"):
            d["merchant_name"] = parsed.get("merchant_name") or parsed.get("merchant") or None
        if d.get("total") is None:
            d["total"] = parsed.get("total")
        if not d.get("purchase_date"):
            d["purchase_date"] = _coerce_iso_from_mmddyy(parsed.get("purchase_date_mmddyy") or parsed.get("purchase_date"))
        if not d.get("parse_status"):
            d["parse_status"] = "parsed" if parsed else "uploaded"
        if d.get("confidence") is None and isinstance(ocr, dict):
            try:
                d["confidence"] = float((ocr.get("winner") or {}).get("score"))
            except Exception:
                d["confidence"] = None
        receipts.append(d)
    return {"ok": True, "receipts": receipts}


@router.get("/receipts/{receipt_id}")
def get_receipt(receipt_id: str):
    tid = current_tenant_id()
    with with_db_cursor() as (_, cur):
        cols = _table_columns(cur, "receipts")
        tenant_where, tenant_params = _tenant_where(cols, tid)
        cur.execute(
            f"SELECT * FROM receipts WHERE id = %s AND {tenant_where}",
            tuple([receipt_id, *tenant_params]),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not Found")
    d = dict(row)
    parsed, _ = _extract_parsed_from_row(d)
    d["parsed_json"] = parsed
    return d


@router.get("/receipts/{receipt_id}/parsed")
def get_receipt_parsed(receipt_id: str):
    tid = current_tenant_id()
    with with_db_cursor() as (_, cur):
        cols = _table_columns(cur, "receipts")
        tenant_where, tenant_params = _tenant_where(cols, tid)
        select_cols = [c for c in ("parsed_json", "ocr_json") if c in cols]
        if not select_cols:
            raise HTTPException(status_code=404, detail="Not Found")
        cur.execute(
            f"SELECT {', '.join(select_cols)} FROM receipts WHERE id = %s AND {tenant_where}",
            tuple([receipt_id, *tenant_params]),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not Found")
    parsed, _ = _extract_parsed_from_row(dict(row))
    return {"ok": True, "parsed": parsed}


@router.get("/receipts/{receipt_id}/ocr_debug")
def get_receipt_ocr_debug(receipt_id: str):
    p = os.path.join(_get_receipts_data_dir(), receipt_id, "ocr.json")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Not Found")
    with open(p, "r", encoding="utf-8") as f:
        ocr = json.load(f)
    return {"ok": True, "ocr": ocr}


@router.get("/receipts/{receipt_id}/image")
def get_receipt_image(receipt_id: str):
    tid = current_tenant_id()
    with with_db_cursor() as (_, cur):
        cols = _table_columns(cur, "receipts")
        tenant_where, tenant_params = _tenant_where(cols, tid)
        select_cols = ["id"]
        if "file_path" in cols:
            select_cols.append("file_path")
        if "image_path" in cols:
            select_cols.append("image_path")
        cur.execute(
            f"SELECT {', '.join(select_cols)} FROM receipts WHERE id = %s AND {tenant_where}",
            tuple([receipt_id, *tenant_params]),
        )
        row = cur.fetchone()
    if row:
        p = _receipt_image_path_from_row(dict(row))
        if p and os.path.exists(p):
            return FileResponse(p)

    fallback = os.path.join(_get_receipts_data_dir(), receipt_id, "orig.jpg")
    if os.path.exists(fallback):
        return FileResponse(fallback)
    raise HTTPException(status_code=404, detail="Receipt not found")


@router.get("/receipts/{receipt_id}/debug/{filename}")
def get_debug_file(receipt_id: str, filename: str):
    name = os.path.basename(str(filename or ""))
    if not name or name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    p = os.path.join(_get_receipts_data_dir(), receipt_id, "debug", name)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Debug file not found")
    return FileResponse(p)


@router.post("/receipts/{receipt_id}/reprocess")
def reprocess_receipt(receipt_id: str):
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cols = _table_columns(cur, "receipts")
        tenant_where, tenant_params = _tenant_where(cols, tid)
        cur.execute(
            f"SELECT * FROM receipts WHERE id = %s AND {tenant_where}",
            tuple([receipt_id, *tenant_params]),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not Found")

        d = dict(row)
        image_path = _receipt_image_path_from_row(d) or os.path.join(_get_receipts_data_dir(), receipt_id, "orig.jpg")
        if not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Receipt image not found")

        ocr = _get_receipt_ocr_runner()(receipt_id, image_path)
        parsed = (ocr.get("parsed") if isinstance(ocr.get("parsed"), dict) else {}) or {}
        purchase_iso = _coerce_iso_from_mmddyy(parsed.get("purchase_date_mmddyy") or parsed.get("purchase_date"))
        updates: dict[str, Any] = {}
        if "parsed_json" in cols:
            updates["parsed_json"] = json.dumps(parsed, ensure_ascii=False)
        if "ocr_json" in cols:
            updates["ocr_json"] = json.dumps(ocr, ensure_ascii=False)
        if "merchant_name" in cols:
            updates["merchant_name"] = parsed.get("merchant")
        if "purchase_date" in cols:
            updates["purchase_date"] = purchase_iso
        if "total" in cols:
            updates["total"] = parsed.get("total")
        if "parse_status" in cols:
            updates["parse_status"] = "parsed"
        if updates:
            set_sql = ", ".join([f"{k} = %s" for k in updates.keys()])
            cur.execute(
                f"UPDATE receipts SET {set_sql} WHERE id = %s AND {tenant_where}",
                tuple([*updates.values(), receipt_id, *tenant_params]),
            )
            conn.commit()

    receipt_dir = os.path.join(_get_receipts_data_dir(), receipt_id)
    try:
        with open(os.path.join(receipt_dir, "ocr.json"), "w", encoding="utf-8") as f:
            json.dump(ocr, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return {"ok": True}


@router.post("/receipts/{receipt_id}/verify")
def verify_receipt(receipt_id: str, payload: dict[str, Any] = Body(...)):
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        cols = _table_columns(cur, "receipts")
        tenant_where, tenant_params = _tenant_where(cols, tid)
        cur.execute(
            f"SELECT * FROM receipts WHERE id = %s AND {tenant_where}",
            tuple([receipt_id, *tenant_params]),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not Found")
        d = dict(row)
        parsed, _ = _extract_parsed_from_row(d)

        merchant = str(payload.get("merchant_name") or "").strip() or None
        purchase_raw = str(payload.get("purchase_date") or "").strip() or None
        purchase_iso = _coerce_iso_from_mmddyy(purchase_raw)
        total = payload.get("total")
        try:
            total = float(total) if total is not None else None
        except Exception:
            total = None

        if merchant is not None:
            parsed["merchant"] = merchant
            parsed["merchant_name"] = merchant
        if purchase_raw:
            if re.match(r"^\d{2}/\d{2}/\d{2}$", purchase_raw):
                parsed["purchase_date_mmddyy"] = purchase_raw
            if purchase_iso:
                parsed["purchase_date"] = purchase_iso
        if total is not None:
            parsed["total"] = total

        updates: dict[str, Any] = {}
        if "merchant_name" in cols:
            updates["merchant_name"] = merchant
        if "purchase_date" in cols:
            updates["purchase_date"] = purchase_iso
        if "total" in cols:
            updates["total"] = total
        if "parsed_json" in cols:
            updates["parsed_json"] = json.dumps(parsed, ensure_ascii=False)
        if "verified_json" in cols:
            updates["verified_json"] = json.dumps(
                {
                    "merchant_name": merchant,
                    "purchase_date": purchase_raw,
                    "total": total,
                    "verified_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                ensure_ascii=False,
            )
        if updates:
            set_sql = ", ".join([f"{k} = %s" for k in updates.keys()])
            cur.execute(
                f"UPDATE receipts SET {set_sql} WHERE id = %s AND {tenant_where}",
                tuple([*updates.values(), receipt_id, *tenant_params]),
            )
            conn.commit()
    return {"ok": True}


@router.get("/receipts/{receipt_id}/candidates")
def receipt_candidates(receipt_id: str):
    tid = current_tenant_id()
    with with_db_cursor() as (_, cur):
        r_cols = _table_columns(cur, "receipts")
        t_cols = _table_columns(cur, "transactions")
        if not r_cols or not t_cols:
            return {"ok": True, "candidates": []}

        r_tenant_where, r_tenant_params = _tenant_where(r_cols, tid)
        cur.execute(
            f"SELECT * FROM receipts WHERE id = %s AND {r_tenant_where}",
            tuple([receipt_id, *r_tenant_params]),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not Found")
        receipt = dict(row)
        parsed, _ = _extract_parsed_from_row(receipt)

        receipt_total = parsed.get("total")
        try:
            receipt_total = float(receipt_total) if receipt_total is not None else None
        except Exception:
            receipt_total = None
        receipt_date = _parse_receipt_mmddyy(parsed.get("purchase_date_mmddyy"))
        receipt_merchant = str(parsed.get("merchant") or receipt.get("merchant_name") or "").strip()

        tx_where_parts = []
        tx_params: list[Any] = []
        t_tenant_where, t_tenant_params = _tenant_where(t_cols, tid)
        tx_where_parts.append(t_tenant_where)
        tx_params.extend(t_tenant_params)
        if receipt_total is not None:
            tx_where_parts.append("(abs(amount::double precision - %s) <= 2 OR abs(amount::double precision + %s) <= 2)")
            tx_params.extend([float(receipt_total), float(receipt_total)])

        cur.execute(
            f"""
            SELECT
              id,
              merchant,
              amount::double precision AS amount,
              category,
              purchasedate AS "purchaseDate",
              posteddate AS "postedDate"
            FROM transactions
            WHERE {" AND ".join(tx_where_parts)}
            ORDER BY id DESC
            LIMIT 1200
            """,
            tuple(tx_params),
        )
        tx_rows = cur.fetchall() or []

    out: list[dict[str, Any]] = []
    for r in tx_rows:
        tx = dict(r)
        amt = float(tx.get("amount") or 0.0)
        score = 0.0

        if receipt_total is not None:
            d = min(abs(amt - receipt_total), abs(abs(amt) - receipt_total))
            if d <= 0.01:
                score += 70
            elif d <= 0.10:
                score += 55
            elif d <= 0.50:
                score += 40
            elif d <= 1.00:
                score += 25
            else:
                continue

        if receipt_date is not None:
            tx_date = _parse_tx_date(tx.get("postedDate")) or _parse_tx_date(tx.get("purchaseDate"))
            if tx_date is not None:
                days = abs((tx_date - receipt_date).days)
                if days == 0:
                    score += 25
                elif days == 1:
                    score += 18
                elif days <= 3:
                    score += 10
                elif days <= 7:
                    score += 4
                else:
                    continue

        score += _merchant_overlap_score(receipt_merchant, str(tx.get("merchant") or ""))
        tx["_match_score"] = round(float(score), 2)
        out.append(tx)

    out.sort(key=lambda x: float(x.get("_match_score") or 0.0), reverse=True)
    return {"ok": True, "candidates": out[:50]}


def _attach_receipt_to_tx(tx_id: str, receipt_id: str) -> dict[str, Any]:
    tid = current_tenant_id()
    with with_db_cursor() as (conn, cur):
        r_cols = _table_columns(cur, "receipts")
        tr_cols = _table_columns(cur, "transaction_receipts")
        if not tr_cols:
            raise HTTPException(status_code=500, detail="transaction_receipts table missing")

        r_tenant_where, r_tenant_params = _tenant_where(r_cols, tid)
        cur.execute(
            f"SELECT 1 FROM receipts WHERE id = %s AND {r_tenant_where} LIMIT 1",
            tuple([receipt_id, *r_tenant_params]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Receipt not found")

        values: dict[str, Any] = {"transaction_id": tx_id, "receipt_id": receipt_id}
        if "tenant_id" in tr_cols:
            values["tenant_id"] = int(tid) if tid else None
        cols = list(values.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        conflict_cols = "(transaction_id, receipt_id, tenant_id)" if "tenant_id" in tr_cols else "(transaction_id, receipt_id)"
        cur.execute(
            f"INSERT INTO transaction_receipts ({', '.join(cols)}) VALUES ({placeholders}) ON CONFLICT {conflict_cols} DO NOTHING",
            tuple(values[c] for c in cols),
        )
        conn.commit()
    return {"ok": True}


@router.post("/receipts/attach")
def attach_receipt(payload: dict[str, Any] = Body(...)):
    tx_id = str(payload.get("transaction_id") or "").strip()
    receipt_id = str(payload.get("receipt_id") or "").strip()
    if not tx_id or not receipt_id:
        raise HTTPException(status_code=400, detail="transaction_id and receipt_id required")
    return _attach_receipt_to_tx(tx_id, receipt_id)


@router.post("/transactions/{tx_id}/attach-receipt/{receipt_id}")
def attach_receipt_from_tx(tx_id: str, receipt_id: str):
    tx_id = str(tx_id or "").strip()
    receipt_id = str(receipt_id or "").strip()
    if not tx_id or not receipt_id:
        raise HTTPException(status_code=400, detail="Invalid ids")
    return _attach_receipt_to_tx(tx_id, receipt_id)
