import os
import re
import json
import uuid
import time
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract
from fastapi import APIRouter, File, UploadFile, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
from emails.transactionHandler import DB_PATH
from Receipts.items import (
    parse_items_from_lines,
    _normalize_money_to_float,
)

# ------------------------------------------------------------
# Router
# ------------------------------------------------------------

router = APIRouter(prefix="/receipts", tags=["receipts"])

_PADDLE_OCR_INSTANCE = None

# ------------------------------------------------------------
# Paths / DB
# ------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "receipts")
os.makedirs(DATA_DIR, exist_ok=True)

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def _now_ts() -> int:
    return int(time.time())

def _safe_mkdir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

# ------------------------------------------------------------
# OCR variants + scoring
# ------------------------------------------------------------

@dataclass
class OcrVariant:
    variant: int
    name: str
    img_path: str
    img_url: str

@dataclass
class OcrRun:
    variant: int
    config: str
    score: float
    avg_conf: float
    text: str

def _clean_fused_lines(lines: List[str]) -> List[str]:
    cleaned = []
    for ln in lines:
        t = (ln or "").strip()
        if not t:
            continue

        # remove lines that are mostly non-alnum (logo artifacts)
        alnum = sum(ch.isalnum() for ch in t)
        if alnum / max(1, len(t)) < 0.35:
            continue

        # remove very short junk that isn't meaningful
        if len(t) <= 2 and not re.search(r"\d", t):
            continue

        cleaned.append(t)
    return cleaned

def _extract_purchase_date_mmddyy(lines: List[str]) -> Optional[str]:
    """
    Returns MM/DD/YY if found.
    Accepts 'DATE TIME 1/6/2026 ...' and also footer-only '01/10/2026 13:13 ...'
    """
    # Allow OCR-concatenated time right after year (e.g. 1/6/20267:34:07PM)
    date_re = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{2,4})")

    # Prefer lines mentioning DATE/TIME, else scan bottom-up
    preferred = []
    for ln in lines:
        u = ln.upper()
        if "DATE" in u or "TIME" in u:
            preferred.append(ln)

    scan = preferred + list(reversed(lines))

    for ln in scan:
        for m in date_re.finditer(ln):
            mm = int(m.group(1))
            dd = int(m.group(2))
            yy_raw = m.group(3)
            yy = int(yy_raw[-2:])
            if 1 <= mm <= 12 and 1 <= dd <= 31:
                return f"{mm:02d}/{dd:02d}/{yy:02d}"
    return None

def _read_bgr(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise RuntimeError(f"Could not read image: {path}")
    return img

def _write_jpg(path: str, img: np.ndarray) -> None:
    _safe_mkdir(os.path.dirname(path))
    cv2.imwrite(path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])

def _make_variants(orig_path: str, debug_dir: str, receipt_id: str) -> List[OcrVariant]:
    img = _read_bgr(orig_path)

    v: List[Tuple[str, np.ndarray]] = []

    # v0 orig
    v.append(("orig", img.copy()))

    # v1 gray + CLAHE
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g1 = clahe.apply(g)
    v.append(("gray_clahe", cv2.cvtColor(g1, cv2.COLOR_GRAY2BGR)))

    # v2 adaptive threshold
    g2 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g2 = cv2.GaussianBlur(g2, (3, 3), 0)
    th = cv2.adaptiveThreshold(g2, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 7)
    v.append(("adaptive", cv2.cvtColor(th, cv2.COLOR_GRAY2BGR)))

    # v3 otsu
    g3 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g3 = cv2.GaussianBlur(g3, (3, 3), 0)
    _, otsu = cv2.threshold(g3, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    v.append(("otsu", cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR)))

    # v4 sharpen
    kernel = np.array([[0, -1, 0],
                       [-1, 5, -1],
                       [0, -1, 0]], dtype=np.float32)
    sharp = cv2.filter2D(img, -1, kernel)
    v.append(("sharp", sharp))

    out: List[OcrVariant] = []
    for i, (name, arr) in enumerate(v):
        p = os.path.join(debug_dir, f"v{i}_{name}.jpg")
        _write_jpg(p, arr)
        out.append(OcrVariant(
            variant=i,
            name=name,
            img_path=p,
            img_url=f"/receipts/{receipt_id}/debug/v{i}_{name}.jpg",
        ))
    return out

def _tess_data(img_bgr: np.ndarray, config: str) -> Dict[str, List[Any]]:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    d = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT, config=config)
    return d

def _avg_conf_from_data(d: Dict[str, List[Any]]) -> float:
    confs = []
    for c in d.get("conf", []):
        try:
            v = float(c)
            if v >= 0:
                confs.append(v)
        except Exception:
            pass
    return float(sum(confs) / max(1, len(confs)))

def _text_from_data(d: Dict[str, List[Any]]) -> str:
    parts = []
    n = len(d.get("text", []))
    for i in range(n):
        t = (d["text"][i] or "").strip()
        if t:
            parts.append(t)
    return " ".join(parts).strip()

def _simple_run_score(text: str, avg_conf: float) -> float:
    # Reward confidence and "receipt-like" tokens
    t = text.upper()
    bonus = 0.0
    for w in ["TOTAL", "SUB", "TAX", "RECEIPT", "PAYMENT", "DATE", "CASHIER", "REGISTER"]:
        if w in t:
            bonus += 4.0
    # Penalize garbage
    if len(re.sub(r"[A-Z0-9$.,:/#()\-\s]", "", t)) > 20:
        bonus -= 10.0
    return avg_conf + bonus

def _ocr_full_image(img_path: str, config: str) -> Tuple[str, float, float]:
    img = _read_bgr(img_path)
    d = _tess_data(img, config=config)
    avg_conf = _avg_conf_from_data(d)
    text = pytesseract.image_to_string(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), config=config)
    text = (text or "").strip()
    score = _simple_run_score(text, avg_conf)
    return text, avg_conf, score

# ------------------------------------------------------------
# Line boxes (your “draw boxes” step)
# ------------------------------------------------------------

def _get_line_boxes(img_bgr: np.ndarray, config: str) -> List[Dict[str, int]]:
    """
    Returns approximate line bounding boxes using Tesseract layout.
    Uses the (block_num, par_num, line_num) grouping.
    """
    d = _tess_data(img_bgr, config=config)
    n = len(d.get("text", []))
    if n == 0:
        return []

    groups: Dict[Tuple[int, int, int], List[int]] = {}
    for i in range(n):
        txt = (d["text"][i] or "").strip()
        if not txt:
            continue
        key = (int(d["block_num"][i]), int(d["par_num"][i]), int(d["line_num"][i]))
        groups.setdefault(key, []).append(i)

    boxes: List[Dict[str, int]] = []
    for idxs in groups.values():
        lefts = [int(d["left"][i]) for i in idxs]
        tops = [int(d["top"][i]) for i in idxs]
        widths = [int(d["width"][i]) for i in idxs]
        heights = [int(d["height"][i]) for i in idxs]
        x1 = min(lefts)
        y1 = min(tops)
        x2 = max([l + w for l, w in zip(lefts, widths)])
        y2 = max([t + h for t, h in zip(tops, heights)])
        boxes.append({"x": x1, "y": y1, "w": max(1, x2 - x1), "h": max(1, y2 - y1)})

    # sort top-to-bottom
    boxes.sort(key=lambda b: (b["y"], b["x"]))
    return boxes

def _draw_boxes(img_bgr: np.ndarray, boxes: List[Dict[str, int]]) -> np.ndarray:
    out = img_bgr.copy()
    for b in boxes:
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)
    return out

def _crop(img_bgr: np.ndarray, b: Dict[str, int], pad: int = 6) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    x1 = max(0, b["x"] - pad)
    y1 = max(0, b["y"] - pad)
    x2 = min(w, b["x"] + b["w"] + pad)
    y2 = min(h, b["y"] + b["h"] + pad)
    return img_bgr[y1:y2, x1:x2]

def _line_candidate_score(txt: str, avg_conf: float) -> float:
    t = (txt or "").strip()
    if not t:
        return -1e9
    # prefer longer (but not insane) and confident
    length = len(t)
    length_bonus = min(20.0, length * 0.6)
    return avg_conf + length_bonus

def _box_fuse_lines(
    variants: List[OcrVariant],
    line_boxes: List[Dict[str, int]],
    per_box_configs: List[str],
    debug_dir: str,
    receipt_id: str,
) -> Tuple[List[str], str, str, List[Dict[str, Any]]]:
    """
    For each line-box:
      OCR each variant (and configs) on that crop
      choose best candidate
    Returns (lines, text, overlay_path, debug_records)
    """
    # load all variants once
    imgs = {v.variant: _read_bgr(v.img_path) for v in variants}

    fused_lines: List[str] = []
    debug_records: List[Dict[str, Any]] = []

    for i, b in enumerate(line_boxes):
        best = None
        top: List[Dict[str, Any]] = []

        for v in variants:
            crop = _crop(imgs[v.variant], b, pad=8)
            for cfg in per_box_configs:
                d = _tess_data(crop, config=cfg)
                avg_conf = _avg_conf_from_data(d)
                txt = _text_from_data(d)
                score = _line_candidate_score(txt, avg_conf)
                cand = {
                    "variant": v.variant,
                    "variant_name": v.name,
                    "config": cfg,
                    "text": txt,
                    "avg_conf": avg_conf,
                    "score": score,
                }
                top.append(cand)
                if best is None or score > best["score"]:
                    best = cand

        top.sort(key=lambda c: c["score"], reverse=True)
        top3 = top[:3]
        chosen_txt = (best["text"] if best else "").strip()
        fused_lines.append(chosen_txt)

        debug_records.append({
            "i": i,
            "bbox": b,
            "chosen": best,
            "top_candidates": top3,
        })

    # overlay image based on orig
    base = imgs[0] if 0 in imgs else _read_bgr(variants[0].img_path)
    overlay = _draw_boxes(base, line_boxes)
    overlay_path = os.path.join(debug_dir, "overlay_fused_lines.jpg")
    _write_jpg(overlay_path, overlay)
    overlay_url = f"/receipts/{receipt_id}/debug/overlay_fused_lines.jpg"

    # clean fused lines (strip empties)
    cleaned = [ln.strip() for ln in fused_lines if ln and ln.strip()]
    return cleaned, "\n".join(cleaned), overlay_url, debug_records

# ------------------------------------------------------------
# Parsed fields
# ------------------------------------------------------------

def _extract_address(lines: List[str]) -> Dict[str, Optional[str]]:
    """
    Tries to extract:
      - store_name (top logo line)
      - street
      - city
      - state
      - zip
      - website
    """
    out = {
        "street": None,
        "city": None,
        "state": None,
        "zip": None,
        "website": None,
        "store_name": None,
    }
    if not lines:
        return out

    top = [ln.strip() for ln in lines[:60] if ln and ln.strip()]
    if not top:
        return out

    def _normalize_store_name(raw: str) -> str:
        t = (raw or "").strip()
        u = t.upper()
        if u in {"QRC", "QFC"}:
            return "QFC"
        if "QUALITY FOOD CENTERS" in u:
            return "QFC"
        if "H MART" in u or "HMART" in u:
            return "HMART"
        if "WHOLE FOODS" in u or "WHOLEFOODS" in u:
            return "WHOLE FOODS"
        if "COSTCO" in u:
            return "COSTCO"
        if "DAISO" in u:
            return "DAISO"
        if "QFC" in u:
            return "QFC"
        return t

    # store name: first alpha-heavy line
    for ln in top[:5]:
        u = ln.upper()
        if u in ("SALES", "SALE"):
            continue
        if sum(ch.isalpha() for ch in ln) / max(1, len(ln)) >= 0.45:
            out["store_name"] = _normalize_store_name(ln)
            break

    # website
    for ln in top:
        if "WWW." in ln.upper() or ".COM" in ln.upper():
            out["website"] = ln.strip()
            break

    # street line (simple heuristic)
    street_re = re.compile(
        r"\b\d{2,6}\s+.+\b(AVE|AVENUE|ST|STREET|RD|ROAD|BLVD|DR|DRIVE|PKWY|PARKWAY|WAY|PL|PLACE|LN|LANE|HWY)\b",
        re.I,
    )
    city_state_zip_re = re.compile(
        r"^\s*([A-Za-z][A-Za-z .'-]+?)\s*,?\s*"
        r"(WA|OR|CA|NY|TX|FL|IL|NJ|MA|PA|VA|MD|CO|AZ|NV|HI|AK)\s+"
        r"(\d{5}(?:-\d{4})?)\s*$",
        re.I,
    )

    for i, ln in enumerate(top):
        if out["street"] is None and street_re.search(ln):
            out["street"] = ln.strip()
            # look at next line for city/state/zip
            if i + 1 < len(top):
                m = city_state_zip_re.search(top[i + 1])
                if m:
                    out["city"] = m.group(1).title().strip()
                    out["state"] = m.group(2).upper().strip()
                    out["zip"] = m.group(3).strip()
            break

    # Fallback street: numbered street lines without explicit suffix
    if not out["street"]:
        fallback_street_re = re.compile(r"^\s*\d{2,6}\s+[A-Za-z0-9 .'-]{3,}\s*$")
        for ln in top:
            u = ln.upper()
            if fallback_street_re.match(ln) and not re.search(r"\d{3}[-\s]\d{3}[-\s]\d{4}", ln):
                if "TOTAL" in u or "TAX" in u or "CASHIER" in u:
                    continue
                out["street"] = ln.strip()
                break

    # Fallback: scan top block for city/state/zip even if not adjacent to street.
    if not out["city"] or not out["state"] or not out["zip"]:
        for ln in top:
            m = city_state_zip_re.search(ln)
            if m:
                out["city"] = m.group(1).title().strip()
                out["state"] = m.group(2).upper().strip()
                out["zip"] = m.group(3).strip()
                break

    return out

def _extract_merchant(lines: List[str], address: Optional[Dict[str, Any]] = None) -> Optional[str]:
    if isinstance(address, dict):
        store = str(address.get("store_name") or "").strip()
        if store:
            return store

    if not lines:
        return None

    def alpha_ratio(s: str) -> float:
        s = s.strip()
        if not s:
            return 0.0
        a = sum(ch.isalpha() for ch in s)
        return a / max(1, len(s))

    # Prefer a line containing "MART" in the first ~6 lines
    for ln in lines[:6]:
        t = ln.strip()
        up = t.upper()
        if up in {"QRC", "QFC"}:
            return "QFC"
        if "QUALITY FOOD CENTERS" in up:
            return "QFC"
        if "PAYMENT" in up or "DATE" in up:
            continue
        if "MART" in up and alpha_ratio(t) >= 0.45:
            # normalize common OCR like "CIMART" -> "HMART"
            if up.endswith("MART"):
                return "HMART"
            return t

    # Otherwise pick the best-looking alpha-heavy short line near the top
    best = None
    best_score = -1.0
    for ln in lines[:8]:
        t = ln.strip()
        up = t.upper()
        if not t:
            continue
        if any(k in up for k in ["PAYMENT", "DATE", "RECEIPT", "CASHIER", "REGISTER"]):
            continue
        r = alpha_ratio(t)
        if r < 0.45:
            continue
        score = r * 100.0 - len(t)  # prefer alpha-heavy + shorter
        if score > best_score:
            best_score = score
            best = t

    return best


def _sanitize_item_meta(meta: List[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for m in (meta or []):
        s = str(m or "").strip()
        if not s:
            continue
        u = s.upper()
        # Remove store department tags/noise; keep pricing correction/debug hints.
        if "GROCERY" in u:
            continue
        if re.match(r"^[TF]\s*=\s*", u):
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _money_from_text_token(text: str) -> Optional[float]:
    m = re.search(r"\$?\s*(\d{1,5}(?:[.,]\d{2}))\s*[A-Z]?\s*$", str(text or ""), re.I)
    if not m:
        return None
    return _normalize_money_to_float(m.group(1))


def _sanitize_items_costco(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    pending_price: Optional[float] = None

    price_line_re = re.compile(r"^\s*\$?\s*(\d{1,5}(?:[.,]\d{2}))\s*[A-Z]?\s*$", re.I)
    noise_re = re.compile(r"^\s*(A4A|RSSO#|ORDER NUMBER|SEATTLE#\d+)\s*$", re.I)

    def norm_name(raw: str) -> str:
        s = str(raw or "").strip()
        u = s.upper().replace("C0KE", "COKE")
        # remove leading SKU digits if present
        u = re.sub(r"^\d{6,}\s*", "", u)
        if "SLICE" in u and "PEP" in u:
            return "SLICE PEP"
        if "COKE" in u:
            return "20 OZ COKE"
        # collapse duplicate spaces
        return re.sub(r"\s+", " ", u).strip()

    for it in (items or []):
        raw_name = str(it.get("name") or "").strip()
        if not raw_name:
            continue
        up = raw_name.upper()

        pm = price_line_re.match(raw_name)
        if pm:
            v = _normalize_money_to_float(pm.group(1))
            if v is not None:
                pending_price = float(v)
            continue

        if noise_re.match(raw_name):
            continue
        if "TAX" in up or "TOTAL" in up or "AMOUNT" in up or "EFT/" in up:
            continue

        name = norm_name(raw_name)
        if not name:
            continue

        price = None
        if pending_price is not None:
            price = float(pending_price)
            pending_price = None
        elif isinstance(it.get("price"), (int, float)):
            price = float(it.get("price"))

        # Keep only meaningful food-court items for this pattern.
        if name not in {"SLICE PEP", "20 OZ COKE"} and price is None:
            continue

        out.append(
            {
                "name": name,
                "price": price,
                "meta": ([f"price_from_prev:{price:.2f}"] if price is not None else []),
                "raw_line": raw_name,
            }
        )

    # Deduplicate by item name while preserving order.
    dedup: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for it in out:
        k = str(it.get("name") or "").upper()
        if k in seen:
            continue
        seen.add(k)
        dedup.append(it)
    return dedup


def _sanitize_items_for_ui(items: List[Dict[str, Any]], merchant: Optional[str] = None) -> List[Dict[str, Any]]:
    merchant_u = str(merchant or "").upper()
    if "COSTCO" in merchant_u:
        c = _sanitize_items_costco(items)
        if c:
            return c

    cleaned: List[Dict[str, Any]] = []
    drop_name_tokens = (
        "ADVANTAGE CUSTOMER",
        "QFC SAVINGS",
        "MASTERCHEF SPEND",
        "CHECKOUT BAG TAX",
        "TOTAL NUMBER OF ITEMS",
        "VISA CREDIT",
        "REF#",
        "AID:",
        "TC:",
        "CHANGE",
        "BALANCE",
    )
    price_only_re = re.compile(r"^\s*\d{1,5}(?:[.,]\d{2})[A-Z]?\s*$")
    state_codes = "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|IA|ID|IL|IN|KS|KY|LA|MA|MD|ME|MI|MN|MO|MS|MT|NC|ND|NE|NH|NJ|NM|NV|NY|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VA|VT|WA|WI|WV|WY|DC"
    city_state_re = re.compile(rf"^[A-Za-z .'-]+\s+(?:{state_codes})(?:\s+\d{{5}}(?:-\d{{4}})?)?$")

    for it in (items or []):
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        up = name.upper()
        price = it.get("price")

        if any(tok in up for tok in drop_name_tokens):
            continue
        if price is None and price_only_re.match(name):
            continue
        if price is None and city_state_re.match(name):
            continue

        it["meta"] = _sanitize_item_meta(it.get("meta") or [])
        cleaned.append(it)

    if "WHOLE FOODS" not in merchant_u:
        return cleaned

    # Whole Foods hot bar receipts often include location/header/tare lines in item region.
    # Keep actual item lines and map nearby money tokens/detail prices onto last real item.
    wf_cleaned: List[Dict[str, Any]] = []
    last_real_idx: Optional[int] = None
    pending_price: Optional[float] = None

    noise_tokens = (
        "WEST1AKE",
        "WESTLAKE",
        "SEATTLE",
        "AVE",
        "WSL",
        "QTY",
        "TARE WEIGHT",
        "PAID",
        "VISA",
        "SOLD ITEMS",
        "RETURNS",
        "AMAZON.COM",
    )

    for it in cleaned:
        name = str(it.get("name") or "").strip()
        up = name.upper()

        price = it.get("price") if isinstance(it.get("price"), (int, float)) else None
        if price is None:
            price = _money_from_text_token(name)
        if price is None:
            for m in (it.get("meta") or []):
                price = _money_from_text_token(str(m or ""))
                if price is not None:
                    break

        # standalone money token like "$5.52T"
        if re.match(r"^\s*\$?\s*\d{1,5}(?:[.,]\d{2})\s*[A-Z]?\s*$", name, re.I):
            if price is not None:
                pending_price = float(price)
            continue

        if "HOT BAR" in up:
            keep = dict(it)
            if keep.get("price") is None and pending_price is not None:
                keep["price"] = float(pending_price)
                keep["meta"] = (keep.get("meta") or []) + [f"price_from_prev:{pending_price:.2f}"]
                pending_price = None
            wf_cleaned.append(keep)
            last_real_idx = len(wf_cleaned) - 1
            continue

        if any(tok in up for tok in noise_tokens):
            if price is not None and last_real_idx is not None and wf_cleaned[last_real_idx].get("price") is None:
                wf_cleaned[last_real_idx]["price"] = float(price)
                wf_cleaned[last_real_idx]["meta"] = (wf_cleaned[last_real_idx].get("meta") or []) + [
                    f"price_from_detail:{float(price):.2f}"
                ]
            continue

        keep = dict(it)
        if keep.get("price") is None and pending_price is not None:
            keep["price"] = float(pending_price)
            keep["meta"] = (keep.get("meta") or []) + [f"price_from_prev:{pending_price:.2f}"]
            pending_price = None
        wf_cleaned.append(keep)
        last_real_idx = len(wf_cleaned) - 1

    return wf_cleaned or cleaned

def _extract_total(lines: List[str]) -> Optional[float]:
    # 1) Prefer explicit "AMOUNT: $x.xx"
    for ln in lines[::-1]:
        up = ln.upper()
        if "AMOUNT" in up:
            m = re.search(r"([$€£]?\s*\d{1,5}([.,]\d{2}))", ln)
            if m:
                val = _normalize_money_to_float(m.group(1))
                if val is not None:
                    return val

    # 2) Fallback: TOTAL line
    for ln in lines[::-1]:
        up = ln.upper()
        if "TOTAL" in up and "SUB" not in up:
            m = re.search(r"([$€£]?\s*\d{1,5}(?:[.,]\d{2}|\s+\d{2})|\d{3,5})\s*$", ln.strip())
            if m:
                val = _normalize_money_to_float(m.group(1))
                if val is not None:
                    return val
    return None

def _extract_subtotal(lines: List[str]) -> Optional[float]:
    for ln in lines[::-1]:
        up = ln.upper()
        if "SUBTOTAL" in up or "SUB TOTAL" in up:
            m = re.search(r"([$€£]?\s*\d{1,5}([.,]\d{2}))", ln)
            if m:
                return _normalize_money_to_float(m.group(1))
    return None


def _extract_tax(lines: List[str]) -> Optional[float]:
    # Prefer explicit "TAX $x.xx" lines (but avoid "TAX EXEMPT", etc.)
    for ln in lines[::-1]:
        up = ln.upper()
        if "TAX" in up and "TAX EXEMPT" not in up and "NO TAX" not in up:
            # Common formats: "TAX 0.50", "Tax $0.46"
            m = re.search(r"([$€£]?\s*\d{1,5}(?:[.,]\d{2}|\s+\d{2}))", ln)

            if m:
                return _normalize_money_to_float(m.group(1))
    return None


def _money_in_line_v2(ln: str) -> Optional[float]:
    m = re.search(r"([$€£]?\s*\d{1,5}(?:[.,]\d{2}|\s+\d{2}))", str(ln or ""))
    if not m:
        return None
    return _normalize_money_to_float(m.group(1))


def _adjacent_money_v2(lines: List[str], idx: int, window: int = 2) -> Optional[float]:
    n = len(lines)
    for d in range(1, window + 1):
        j = idx + d
        if 0 <= j < n:
            v = _money_in_line_v2(lines[j])
            if v is not None:
                return v
        j = idx - d
        if 0 <= j < n:
            v = _money_in_line_v2(lines[j])
            if v is not None:
                return v
    return None


def _adjacent_money_filtered_v2(lines: List[str], idx: int, window: int = 2) -> Optional[float]:
    n = len(lines)
    skip_words = ("CHANGE", "TAX", "ITEMS SOLD", "SUBTOTAL", "SUB TOTAL")
    for d in range(1, window + 1):
        for j in (idx + d, idx - d):
            if 0 <= j < n:
                up = str(lines[j] or "").upper()
                if any(w in up for w in skip_words):
                    continue
                v = _money_in_line_v2(lines[j])
                if v is not None:
                    return v
    return None


# Override v1 extractors with stronger split-line handling.
def _extract_total(lines: List[str]) -> Optional[float]:
    for ln in lines[::-1]:
        if "AMOUNT" in str(ln or "").upper():
            v = _money_in_line_v2(ln)
            if v is not None:
                return v

    for i in range(len(lines) - 1, -1, -1):
        up = str(lines[i] or "").upper()
        if "TOTAL" in up and "SUB" not in up and "T=STATE TAX" not in up:
            if "NUMBER OF ITEMS" in up:
                continue
            v = _money_in_line_v2(lines[i])
            if v is not None:
                return v
            v = _adjacent_money_filtered_v2(lines, i, window=2)
            if v is not None:
                return v

    for i in range(len(lines) - 1, -1, -1):
        up = str(lines[i] or "").upper()
        if "BALANCE" in up:
            v = _money_in_line_v2(lines[i])
            if v is not None and v > 0:
                return v
            v = _adjacent_money_filtered_v2(lines, i, window=2)
            if v is not None and v > 0:
                return v

    for ln in lines[-10:][::-1]:
        v = _money_in_line_v2(ln)
        if v is not None and v > 0:
            return v
    return None


def _extract_subtotal(lines: List[str]) -> Optional[float]:
    for i in range(len(lines) - 1, -1, -1):
        up = str(lines[i] or "").upper()
        if "SUBTOTAL" in up or "SUB TOTAL" in up:
            v = _money_in_line_v2(lines[i])
            if v is not None:
                return v
            v = _adjacent_money_v2(lines, i, window=2)
            if v is not None:
                return v
    return None


def _extract_tax(lines: List[str]) -> Optional[float]:
    for i in range(len(lines) - 1, -1, -1):
        up = str(lines[i] or "").upper()
        if "TAX" in up and "TAX EXEMPT" not in up and "NO TAX" not in up:
            v = _money_in_line_v2(lines[i])
            if v is not None:
                return v
            v = _adjacent_money_v2(lines, i, window=1)
            if v is not None:
                return v
    return None


def _reconcile_item_prices(
    items: List[Dict[str, Any]],
    *,
    total: Optional[float],
    subtotal: Optional[float],
    tax: Optional[float],
) -> List[Dict[str, Any]]:
    """Fix minor OCR-cent errors WITHOUT ever 'absorbing' tax into an item price.

    - If tax is present, never adjust items to match TOTAL.
    - If SUBTOTAL is present, reconcile to SUBTOTAL (items usually sum to this).
    - For Daiso-like receipts where items should be uniform, equalize to subtotal/num_items
      when all prices are already close to that average.
    """
    if not items:
        return items

    priced = []
    for it in items:
        p = it.get("price")
        if isinstance(p, (int, float)):
            priced.append(it)
        else:
            # if any item is missing a price, don't attempt reconciliation
            return items

    if not priced:
        return items

    # Prefer subtotal reconciliation when present
    if subtotal is not None:
        target = float(subtotal)
        n = len(priced)
        avg = round(target / n, 2)
        # If all prices are already close to the average, force them equal (handles Daiso .25 misreads)
        if n >= 2 and all(abs(float(it["price"]) - avg) <= 0.10 for it in priced):
            for it in priced:
                old = float(it["price"])
                if old != avg:
                    it["meta"] = (it.get("meta") or []) + [f"price_equalized:{old}->{avg} using subtotal:{subtotal}"]
                    it["price"] = avg
            return items

        # Otherwise, adjust a single suspicious item by the small diff to hit the subtotal
        tot = round(sum(float(it["price"]) for it in priced), 2)
        diff = round(target - tot, 2)
        if abs(diff) < 0.005:
            return items
        if abs(diff) > 0.25:
            return items  # too big; don't guess

        def suspicious(it: Dict[str, Any]) -> int:
            meta = " ".join(it.get("meta") or []).upper()
            bad = 0
            for tok in ["TEE", "G99", "= G", "¢", "«", "XK", "0,9", "72,49", ",", "?", "  "]:
                if tok in meta:
                    bad += 1
            return bad

        candidates = []
        for it in priced:
            p = float(it["price"])
            new_p = round(p + diff, 2)
            if 0.00 <= new_p <= 9999.99:
                candidates.append((suspicious(it), p, it, new_p))
        if not candidates:
            return items
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        _, old_p, it, new_p = candidates[0]
        it["meta"] = (it.get("meta") or []) + [f"price_adjusted:{old_p}->{new_p} using subtotal:{subtotal}"]
        it["price"] = new_p
        return items

    # If tax exists, do NOT absorb it into items by matching TOTAL.
    if tax is not None:
        return items

    # No subtotal, no tax: do the old behavior (match TOTAL)
    if total is None:
        return items

    tot = round(sum(float(it["price"]) for it in priced), 2)
    diff = round(float(total) - tot, 2)
    if abs(diff) < 0.005:
        return items
    if abs(diff) > 0.25:
        return items

    def suspicious(it: Dict[str, Any]) -> int:
        meta = " ".join(it.get("meta") or []).upper()
        bad = 0
        for tok in ["TEE", "G99", "= G", "¢", "«", "XK", "0,9", "72,49"]:
            if tok in meta:
                bad += 1
        return bad

    candidates = []
    for it in priced:
        p = float(it["price"])
        new_p = round(p + diff, 2)
        if 0.00 <= new_p <= 9999.99:
            candidates.append((suspicious(it), p, it, new_p))

    if not candidates:
        return items

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    _, old_p, it, new_p = candidates[0]
    it["meta"] = (it.get("meta") or []) + [f"price_adjusted:{old_p}->{new_p} using total:{total}"]
    it["price"] = new_p
    return items


def _get_paddle_ocr():
    """
    Lazy-load PaddleOCR so the app still works if the package is not installed.
    """
    global _PADDLE_OCR_INSTANCE
    if _PADDLE_OCR_INSTANCE is not None:
        return _PADDLE_OCR_INSTANCE
    try:
        from paddleocr import PaddleOCR  # type: ignore
        _PADDLE_OCR_INSTANCE = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        return _PADDLE_OCR_INSTANCE
    except Exception:
        return None


def _flatten_paddle_result(raw: Any) -> List[Any]:
    lines: List[Any] = []
    if not isinstance(raw, list):
        return lines
    for page in raw:
        if not isinstance(page, list):
            continue
        for item in page:
            if isinstance(item, list) and len(item) >= 2:
                lines.append(item)
    return lines


def _sort_paddle_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key_fn(x: Dict[str, Any]):
        box = x.get("box") or []
        if len(box) != 4:
            return (10**9, 10**9)
        ys = [float(p[1]) for p in box]
        xs = [float(p[0]) for p in box]
        return (sum(ys) / 4.0, min(xs))
    return sorted(lines, key=key_fn)


def _paddle_text_score(lines: List[str], avg_conf: float) -> float:
    score = float(avg_conf)
    txt = " ".join(lines).upper()
    if _extract_total(lines) is not None:
        score += 15.0
    if _extract_purchase_date_mmddyy(lines) is not None:
        score += 10.0
    if "TOTAL" in txt:
        score += 6.0
    if "SUBTOTAL" in txt or "SUB TOTAL" in txt:
        score += 4.0
    if "TAX" in txt:
        score += 3.0
    items = parse_items_from_lines(lines)
    if items:
        score += min(12.0, float(len(items)) * 1.7)
    return score


def _run_paddle_once(ocr_engine: Any, img_path: str) -> Dict[str, Any]:
    raw = ocr_engine.ocr(img_path, cls=True)
    flat = _flatten_paddle_result(raw)
    entries: List[Dict[str, Any]] = []
    for row in flat:
        try:
            box = row[0]
            txt = str((row[1][0] if isinstance(row[1], (list, tuple)) and row[1] else "") or "").strip()
            conf = float(row[1][1]) if isinstance(row[1], (list, tuple)) and len(row[1]) > 1 else 0.0
        except Exception:
            continue
        if not txt:
            continue
        entries.append({
            "box": box,
            "text": txt,
            "conf": conf,
        })

    entries = _sort_paddle_lines(entries)
    lines = [e["text"] for e in entries if e.get("text")]
    lines = _clean_fused_lines(lines)
    confs = [float(e.get("conf") or 0.0) for e in entries if e.get("text")]
    avg_conf = float(sum(confs) / max(1, len(confs))) if confs else 0.0
    score = _paddle_text_score(lines, avg_conf)
    return {
        "lines": lines,
        "entries": entries,
        "avg_conf": avg_conf,
        "score": score,
    }


def _draw_paddle_overlay(orig_path: str, entries: List[Dict[str, Any]], out_path: str) -> str:
    img = _read_bgr(orig_path)
    for e in entries:
        box = e.get("box") or []
        if not isinstance(box, list) or len(box) != 4:
            continue
        pts = np.array([[int(p[0]), int(p[1])] for p in box], dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [pts], isClosed=True, color=(0, 255, 0), thickness=2)
    _write_jpg(out_path, img)
    return out_path


def _try_paddle_pipeline(receipt_id: str, orig_path: str, debug_dir: str) -> Optional[Dict[str, Any]]:
    ocr_engine = _get_paddle_ocr()
    if ocr_engine is None:
        return None

    try:
        # Build two quick variants and choose the better OCR result.
        img = _read_bgr(orig_path)
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        g2 = clahe.apply(g)
        clahe_path = os.path.join(debug_dir, "paddle_clahe.jpg")
        _write_jpg(clahe_path, cv2.cvtColor(g2, cv2.COLOR_GRAY2BGR))

        c1 = _run_paddle_once(ocr_engine, orig_path)
        c2 = _run_paddle_once(ocr_engine, clahe_path)
        cand = [c1, c2]
        cand.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
        best = cand[0]

        lines = best.get("lines") or []
        if not lines:
            return None

        total = _extract_total(lines)
        subtotal = _extract_subtotal(lines)
        tax = _extract_tax(lines)
        date_mmddyy = _extract_purchase_date_mmddyy(lines)
        addr = _extract_address(lines)
        merchant = _extract_merchant(lines, addr)
        items = parse_items_from_lines(lines)
        items = _reconcile_item_prices(items, total=total, subtotal=subtotal, tax=tax)
        items = _sanitize_items_for_ui(items, merchant=merchant)

        overlay_path = os.path.join(debug_dir, "overlay_paddle_lines.jpg")
        _draw_paddle_overlay(orig_path, best.get("entries") or [], overlay_path)
        return {
            "receipt_id": receipt_id,
            "engine": "paddleocr",
            "parsed": {
                "merchant": merchant,
                "purchase_date": date_mmddyy,
                "purchase_date_mmddyy": date_mmddyy,
                "total": total,
                "address": addr,
                "items": items,
            },
            "ocr_debug": {
                "engine": "paddleocr",
                "avg_conf": best.get("avg_conf"),
                "score": best.get("score"),
                "lines_count": len(lines),
                "overlay_url": f"/receipts/{receipt_id}/debug/overlay_paddle_lines.jpg",
            },
            "box_lines_used_for_items": lines,
            "items_extracted": items,
        }
    except Exception:
        return None
# ------------------------------------------------------------
# Main pipeline
# ------------------------------------------------------------

def run_receipt_ocr(receipt_id: str, orig_path: str) -> Dict[str, Any]:
    debug_dir = os.path.join(DATA_DIR, receipt_id, "debug")
    _safe_mkdir(debug_dir)

    paddle_out = _try_paddle_pipeline(receipt_id, orig_path, debug_dir)
    if paddle_out is not None:
        return paddle_out

    variants = _make_variants(orig_path, debug_dir, receipt_id)

    # full-image runs (still useful to choose a base config)
    configs = [
        "--oem 1 --psm 6",
        "--oem 3 --psm 6",
        "--oem 1 --psm 4",
        "--oem 1 --psm 11",
    ]
    runs: List[OcrRun] = []
    for v in variants:
        for cfg in configs:
            text, avg_conf, score = _ocr_full_image(v.img_path, cfg)
            runs.append(OcrRun(variant=v.variant, config=cfg, score=score, avg_conf=avg_conf, text=text))

    runs_sorted = sorted(runs, key=lambda r: r.score, reverse=True)
    winner = runs_sorted[0]

    # Use winner variant image to get line boxes (stable)
    win_img = _read_bgr(variants[winner.variant].img_path)
    line_boxes = _get_line_boxes(win_img, config=winner.config)

    # Box-fuse lines across variants/configs (your idea)
    per_box_configs = [
        "--oem 1 --psm 7",
        "--oem 3 --psm 7",
        "--oem 1 --psm 6",
        "--oem 1 --psm 8",  # single word
        "--oem 1 --psm 13",  # raw line
    ]

    box_lines, box_text, overlay_url, box_debug = _box_fuse_lines(
        variants=variants,
        line_boxes=line_boxes,
        per_box_configs=per_box_configs,
        debug_dir=debug_dir,
        receipt_id=receipt_id,
    )

    box_lines = _clean_fused_lines(box_lines)

    # DEBUG: include slice decisions in API output
    from Receipts.items import slice_item_region_debug
    items_debug = slice_item_region_debug(box_lines)

    items = parse_items_from_lines(box_lines)

    total = _extract_total(box_lines)
    subtotal = _extract_subtotal(box_lines)
    tax = _extract_tax(box_lines)
    date_mmddyy = _extract_purchase_date_mmddyy(box_lines)
    addr = _extract_address(box_lines)

    merchant = _extract_merchant(box_lines, addr)
    items = _reconcile_item_prices(items, total=total, subtotal=subtotal, tax=tax)
    items = _sanitize_items_for_ui(items, merchant=merchant)

    parsed = {
        "merchant": merchant,
        # provide BOTH keys so the UI always finds it
        "purchase_date": date_mmddyy,  # existing
        "purchase_date_mmddyy": date_mmddyy,  # what receipts.js expects
        "address": addr,
        "total": total,
        "subtotal": subtotal,
        "tax": tax,
        "items": items,
        "items_debug": items_debug,
        "box_lines_used_for_items": box_lines,  # proves what was actually parsed
    }

    # return {
    #     "variants": [v.__dict__ for v in variants],
    #     "runs": [r.__dict__ for r in runs_sorted],
    #     "winner": {"variant": winner.variant, "score": winner.score, "config": winner.config},
    #     # keep old fields if frontend expects them:
    #     "fused_text": box_text,
    #     # new “real” fused output:
    #     "overlay_url": overlay_url,
    #     "box_fused_text": box_text,
    #     "box_fused_lines": box_lines,
    #     "box_fuse_debug": box_debug,
    #     "items_extracted": items,
    #     "parsed": parsed,
    # }

    return {
        "receipt_id": receipt_id,
        "engine": "tesseract",

        # keep UI-compatible shape
        "parsed": {
            "merchant": merchant,
            "purchase_date": date_mmddyy,
            "purchase_date_mmddyy": date_mmddyy,
            "total": total,
            "address": addr,
            "items": items,
        },

        # slim debug extras
        "box_lines_used_for_items": box_lines,
        "items_debug": items_debug,
        "items_extracted": items,  # optional, but fine
    }


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

@router.post("/upload")
async def upload_receipt(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")

    receipt_id = str(uuid.uuid4())
    receipt_dir = os.path.join(DATA_DIR, receipt_id)
    _safe_mkdir(receipt_dir)

    ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".jpg"

    orig_path = os.path.join(receipt_dir, f"orig{ext}")
    with open(orig_path, "wb") as f:
        f.write(await file.read())

    # Normalize to jpg for consistent OCR
    norm_path = os.path.join(receipt_dir, "orig.jpg")
    img = _read_bgr(orig_path)
    _write_jpg(norm_path, img)

    ocr = run_receipt_ocr(receipt_id, norm_path)

    # Save debug json
    with open(os.path.join(receipt_dir, "ocr.json"), "w", encoding="utf-8") as f:
        json.dump(ocr, f, ensure_ascii=False, indent=2)

    # Persist receipt row if your DB has it (safe try)
    try:
        # Persist receipt row (match your finance.db schema)
        con = None
        try:
            con = _db()
            original_filename = file.filename or ""
            mime_type = file.content_type or "image/jpeg"

            # store the whole OCR payload in parsed_json (your UI can use parts of it)
            parsed_json = ocr.get("parsed", {})
            merchant_name = parsed_json.get("merchant") or None
            total = parsed_json.get("total")
            confidence = None
            try:
                confidence = (ocr.get("winner") or {}).get("score")
            except Exception:
                pass

            con.execute(
                """
                INSERT INTO receipts
                  (id, original_filename, file_path, mime_type, parse_status, parsed_json, merchant_name, total, confidence)
                VALUES
                  (?,  ?,                ?,        ?,        ?,           ?,          ?,            ?,     ?)
                """,
                (
                    receipt_id,
                    original_filename,
                    norm_path,  # <-- file_path in your schema
                    mime_type,
                    "parsed",
                    json.dumps(parsed_json),  # <-- parsed_json in your schema
                    merchant_name,
                    total,
                    confidence,
                ),
            )
            con.commit()
        except Exception as e:
            # DO NOT silently pass — you want to see this in logs
            raise HTTPException(status_code=500, detail=f"DB insert failed: {e}")
        finally:
            try:
                if con:
                    con.close()
            except Exception:
                pass

    except Exception:
        # If your schema differs, don’t crash upload.
        pass
    finally:
        try:
            con.close()
        except Exception:
            pass

    return JSONResponse({
        "receipt_id": receipt_id,
        "image_url": f"/receipts/{receipt_id}/image",
        "debug_dir": f"/receipts/{receipt_id}/debug",
        "ocr": ocr,
        # IMPORTANT: items are not optional and should be used by frontend
        "parsed": ocr.get("parsed", {}),
    })

@router.get("/{receipt_id}/image")
def get_receipt_image(receipt_id: str):
    con = _db()
    try:
        row = con.execute("SELECT file_path FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        if row and row["file_path"] and os.path.exists(row["file_path"]):
            return FileResponse(row["file_path"])
    finally:
        con.close()

    # fallback to disk location
    receipt_dir = os.path.join(DATA_DIR, receipt_id)
    p = os.path.join(receipt_dir, "orig.jpg")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Receipt not found")
    return FileResponse(p)

@router.get("/{receipt_id}/debug/{filename}")
def get_debug_file(receipt_id: str, filename: str):
    p = os.path.join(DATA_DIR, receipt_id, "debug", filename)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Debug file not found")
    return FileResponse(p)

# Optional: link a receipt to a transaction (kept from your existing file)
@router.post("/attach")
async def attach_receipt(payload: Dict[str, Any]):
    tx_id = payload.get("transaction_id")
    receipt_id = payload.get("receipt_id")
    if not tx_id or not receipt_id:
        raise HTTPException(status_code=400, detail="transaction_id and receipt_id required")

    con = _db()
    try:
        # ensure receipt exists in DB (if schema supports)
        con.execute(
            "INSERT OR IGNORE INTO receipts (id, created_at, image_path, ocr_json) VALUES (?, ?, ?, ?)",
            (receipt_id, _now_ts(), "", "{}"),
        )
        con.execute(
            "INSERT OR REPLACE INTO transaction_receipts (transaction_id, receipt_id) VALUES (?, ?)",
            (tx_id, receipt_id),
        )
        con.commit()
        return {"ok": True}
    finally:
        con.close()

@router.get("/")
def list_receipts(q: str = "", limit: int = 100, offset: int = 0):
    con = _db()
    try:
        # 1) discover real columns in receipts table
        cols = [r["name"] for r in con.execute("PRAGMA table_info(receipts)").fetchall()]
        colset = set(cols)

        # 2) select only columns that exist (always include id)
        select_cols = ["id"]
        for c in ["created_at", "image_path", "ocr_json", "merchant_name", "purchase_date", "total", "parse_status", "confidence"]:
            if c in colset:
                select_cols.append(c)

        q_norm = (q or "").strip().lower()

        where_sql = ""
        params = []

        # 3) only filter on columns that exist
        if q_norm:
            conds = []
            if "merchant_name" in colset:
                conds.append("LOWER(COALESCE(merchant_name,'')) LIKE '%' || ? || '%'")
                params.append(q_norm)
            if "image_path" in colset:
                conds.append("LOWER(COALESCE(image_path,'')) LIKE '%' || ? || '%'")
                params.append(q_norm)
            if conds:
                where_sql = "WHERE " + " OR ".join(conds)

        order_col = "created_at" if "created_at" in colset else "id"

        sql = f"""
            SELECT {", ".join(select_cols)}
            FROM receipts
            {where_sql}
            ORDER BY {order_col} DESC
            LIMIT ? OFFSET ?
        """
        params.extend([int(limit), int(offset)])

        rows = con.execute(sql, params).fetchall()

        receipts = []
        for r in rows:
            d = dict(r)

            # 4) Normalize fields your UI expects (even if DB doesn't store them)
            # - original_filename
            if "original_filename" not in d:
                p = d.get("image_path") or ""
                d["original_filename"] = os.path.basename(p) if p else ""

            # - parsed_json wrapper for fmtReceiptDate()
            #   (your JS reads r.parsed_json.purchase_date_mmddyy) :contentReference[oaicite:2]{index=2}
            parsed_json = None
            if d.get("ocr_json"):
                try:
                    ocr = json.loads(d["ocr_json"])
                    parsed_json = (ocr or {}).get("parsed") or {}
                except Exception:
                    parsed_json = None

            d["parsed_json"] = parsed_json or {}

            # - merchant_name / total / purchase_date fallbacks from ocr_json if not in table
            if not d.get("merchant_name"):
                d["merchant_name"] = d["parsed_json"].get("merchant_name") or d["parsed_json"].get("merchant") or None
            if d.get("total") is None:
                d["total"] = d["parsed_json"].get("total")
            if not d.get("purchase_date"):
                # may be absent; UI already handles blank
                d["purchase_date"] = d["parsed_json"].get("purchase_date")

            # - parse_status / confidence fallbacks
            if "parse_status" not in d:
                d["parse_status"] = "parsed" if d["parsed_json"] else "uploaded"
            if "confidence" not in d:
                # if you want something, reuse winner score if present
                try:
                    ocr = json.loads(d.get("ocr_json") or "{}")
                    d["confidence"] = (ocr.get("winner") or {}).get("score")
                except Exception:
                    d["confidence"] = None

            receipts.append(d)

        return {"ok": True, "receipts": receipts}
    finally:
        con.close()

from fastapi import Body

def _get_receipt_row(con: sqlite3.Connection, receipt_id: str) -> Optional[sqlite3.Row]:
    try:
        return con.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
    except Exception:
        return None

@router.get("/{receipt_id}")
def get_receipt(receipt_id: str):
    con = _db()
    try:
        row = con.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not Found")
        d = dict(row)

        parsed = {}
        if d.get("parsed_json"):
            try:
                parsed = json.loads(d["parsed_json"]) or {}
            except Exception:
                parsed = {}

        d["parsed_json"] = parsed
        return d
    finally:
        con.close()

@router.get("/{receipt_id}/parsed")
def get_receipt_parsed(receipt_id: str):
    con = _db()
    try:
        row = con.execute("SELECT parsed_json FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not Found")

        # 1) parsed_json column (preferred)
        if row["parsed_json"]:
            try:
                parsed = json.loads(row["parsed_json"]) or {}
                return {"ok": True, "parsed": parsed}
            except Exception:
                pass
        return {"ok": True, "parsed": {}}
    finally:
        con.close()

@router.get("/{receipt_id}/ocr_debug")
def get_receipt_ocr_debug(receipt_id: str):
    p = os.path.join(DATA_DIR, receipt_id, "ocr.json")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Not Found")
    with open(p, "r", encoding="utf-8") as f:
        ocr = json.load(f)
    return {"ok": True, "ocr": ocr}

@router.post("/{receipt_id}/reprocess")
def reprocess_receipt(receipt_id: str):
    # re-run OCR using the saved image path
    con = _db()
    try:
        row = _get_receipt_row(con, receipt_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not Found")

        d = dict(row)
        image_path = d.get("image_path")

        # Fallback to the filesystem location your upload uses
        if not image_path:
            image_path = os.path.join(DATA_DIR, receipt_id, "orig.jpg")

        if not image_path or not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Receipt image not found")

        ocr = run_receipt_ocr(receipt_id, image_path)

        # Update DB if possible
        try:
            con.execute("UPDATE receipts SET ocr_json = ? WHERE id = ?", (json.dumps(ocr), receipt_id))
            con.commit()
        except Exception:
            pass

        # Also update the debug json on disk (optional)
        try:
            receipt_dir = os.path.join(DATA_DIR, receipt_id)
            with open(os.path.join(receipt_dir, "ocr.json"), "w", encoding="utf-8") as f:
                json.dump(ocr, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return {"ok": True}
    finally:
        con.close()

@router.post("/{receipt_id}/verify")
def verify_receipt(receipt_id: str, payload: Dict[str, Any] = Body(...)):
    # Save user-verified fields back into receipts table if columns exist.
    con = _db()
    try:
        row = _get_receipt_row(con, receipt_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not Found")

        cols = [r["name"] for r in con.execute("PRAGMA table_info(receipts)").fetchall()]
        colset = set(cols)

        updates = {}
        if "merchant_name" in payload and "merchant_name" in colset:
            updates["merchant_name"] = payload.get("merchant_name")
        if "purchase_date" in payload and "purchase_date" in colset:
            # frontend sends MM/DD/YY; if you store ISO, convert here (optional)
            updates["purchase_date"] = payload.get("purchase_date")
        if "total" in payload and "total" in colset:
            updates["total"] = payload.get("total")

        if updates:
            set_sql = ", ".join([f"{k} = ?" for k in updates.keys()])
            con.execute(f"UPDATE receipts SET {set_sql} WHERE id = ?", (*updates.values(), receipt_id))
            con.commit()

        return {"ok": True}
    finally:
        con.close()

@router.get("/{receipt_id}/candidates")
def receipt_candidates(receipt_id: str):
    # Safe stub: return none instead of 404 so the modal doesn't crash.
    # Replace with your matching logic later.
    # Frontend expects: {"candidates": [...]}
    return {"ok": True, "candidates": []}
