# Receipts/items.py
import math
import re
from typing import Any, Dict, List, Optional

_WORD = lambda w: re.compile(rf"\b{re.escape(w)}\b", re.I)

_DATE_W = _WORD("DATE")
_TIME_W = _WORD("TIME")
_RECEIPT_W = _WORD("RECEIPT")
_REGISTER_W = _WORD("REGISTER")
_ORDER_W = _WORD("ORDER")
_CASHIER_W = _WORD("CASHIER")
_SALES_W = _WORD("SALES")

_PRICE_RE = re.compile(r"(?<!\d)(\d{1,5}([.,]\d{2})?)(?!\d)")
_MONEY_LINE_RE = re.compile(r"[$€£]?\s*\d{1,5}([.,]\d{2})\s*$")
_COSTCO_QTY_AT_RE = re.compile(r"^\s*(\d+)\s*@\s*(\d{1,5}[.,]\d{2})\s*$", re.I)
_COSTCO_ITEM_RE = re.compile(
    r"^\s*(\d{5,})\s+(.+?)\s+(\d{1,5}[.,]\d{2})\s*([A-Z])?\s*$", re.I
)

# price at end of line like "... 6.99" or "... $6.99"
_MONEY_AT_END_RE = re.compile(r"([$€£]?\s*\d{1,5}([.,]\d{2})|\d{3,5})\s*$")

# if you want to keep this flag, here's a safe version
_QTY_AT_PRICE_RE = re.compile(r"^\s*\d+\s*@\s*\d{1,5}([.,]\d{2})\s*$", re.I)


def _is_footer_marker(t: str) -> bool:
    u = (t or "").upper()
    return any(k in u for k in [
        "SUBTOTAL", "SUB TOTAL", "TOTAL", "TAX", "BALANCE",
        "AMOUNT", "APPROVED", "DECLINED", "EFT", "DEBIT", "CREDIT",
        "AID:", "TRAN ID", "CARD", "VERIFIED BY", "CHANGE", "CASH"
    ])


def _looks_like_item_line(t: str) -> bool:
    if not t:
        return False

    u = t.upper()
    if _is_separator_line(t) or _is_legend_line(t):
        return False

    # qty@price pattern, common on Costco: "2@1.99"
    if re.search(r"\b\d+\s*@\s*\d{1,5}([.,]\d{2})\b", u):
        return True

    # ends with a price and has some letters in the description
    if _MONEY_LINE_RE.search(t) and re.search(r"[A-Z]{2,}", u):
        return True

    BAD_ITEM_TOKENS = [
        "PAYMENT", "METHOD", "RECEIPT", "CASHIER", "REGISTER",
        "DATE", "TIME", "CARD", "ACCOUNT", "APPROVED", "DECLINED",
        "SUBTOTAL", "SUB TOTAL", "TOTAL", "TAX",
    ]

    if any(tok in u for tok in BAD_ITEM_TOKENS):
        return False

    # fallback: letters + digits but not total lines
    if re.search(r"[A-Z]{2,}", u) and re.search(r"\d", u) and not _is_totalish(t):
        return True

    return False


def _normalize_money_to_float(s: str) -> Optional[float]:
    """
    Accepts: "6.99", "6,99", "$ 6,99", "699" (-> 6.99), "948" (-> 9.48)
    Returns float dollars or None.
    """
    if not s:
        return None
    t = s.strip()
    t = t.replace(" ", "")
    t = t.replace("$", "").replace("€", "").replace("£", "")
    t = t.replace("\\", "").replace("¢", "")

    # If contains comma but no dot -> treat comma as decimal
    if "," in t and "." not in t:
        t = t.replace(",", ".")
    else:
        t = t.replace(",", "")  # thousands sep

    # Now if pure digits and length >= 3, treat as cents
    if re.fullmatch(r"\d{3,5}", t):
        try:
            cents = int(t)
            return cents / 100.0
        except Exception:
            return None

    try:
        return float(t)
    except Exception:
        return None


def _extract_price_loose(line: str) -> Optional[float]:
    """
    Extract a price from messy OCR lines like:
      "** GROCERY (F) $ = G99"  -> 6.99
      "** GROCERY (F) tee 7 49" -> 7.49
    """
    if not line:
        return None

    t = line.strip().upper()

    # focus on the tail (prices are almost always at the end)
    tail = t[-18:]

    # common OCR confusions
    tail = tail.replace("O", "0").replace("Q", "0")
    tail = tail.replace("I", "1").replace("L", "1").replace("|", "1")
    tail = tail.replace("S", "5")
    tail = tail.replace("B", "8")
    tail = tail.replace("Z", "2")
    tail = tail.replace("G", "6")  # key for your receipt: G99 -> 699

    # remove currency/garbage but keep digits, dot, comma, spaces
    tail = re.sub(r"[^0-9.,\s]", " ", tail)
    tail = re.sub(r"\s+", " ", tail).strip()

    # try explicit decimal (e.g., "6.99" / "6,99")
    m = re.search(r"(\d{1,5}[.,]\d{2})\s*$", tail)
    if m:
        return _normalize_money_to_float(m.group(1))

    # try spaced cents like "7 49" => "749"
    m = re.search(r"(\d)\s+(\d{2})\s*$", tail)
    if m:
        return _normalize_money_to_float(m.group(1) + m.group(2))

    # try bare cents at end like "699" / "249"
    m = re.search(r"(\d{3,5})\s*$", tail)
    if m:
        return _normalize_money_to_float(m.group(1))

    return None


def _clean_meta_tag(line: str) -> str:
    u = (line or "").upper()
    if "GROCERY" in u:
        # preserve "(F)" when present
        return "GROCERY (F)" if "(F" in u else "GROCERY"
    return (line or "").strip()


def _clean_item_name(desc: str) -> str:
    d = (desc or "").strip()
    d = re.sub(r"\s+\d+([.,]\d+)?\s*(OZ|OZ\.|LB|LBS|CT|PK|EA|PC|PCS)\b.*$", "", d, flags=re.I)
    d = re.sub(r"\s+\d+([.,]\d+)?\s*(OZ|OZ\.|LB|LBS)\s*\d*\s*[A-Z]{0,2}\s*$", "", d, flags=re.I)
    d = re.sub(r"\s+\d+\s*$", "", d)  # trailing quantity
    return d.strip()


def _is_metadata_line(line: str) -> bool:
    """
    Treat ** GROCERY (F) as metadata (not an item).
    """
    t = (line or "").strip().upper()
    if "GROCERY" in t and "(F" in t:
        return True
    if t.startswith("*") and "GROCERY" in t:
        return True
    return False


def _is_legend_line(line: str) -> bool:
    t = (line or "").strip().upper()
    # matches "T = STATE TAX ITEM", "F = FOODSTAMP ITEM", and OCR variations
    if re.match(r"^[TF]\s*=\s*", t):
        return True
    if "FOODSTAMP" in t or "FOODSTAHP" in t:
        return True
    if "STATE TAX" in t:
        return True
    return False


def _is_separator_line(line: str) -> bool:
    t = (line or "").strip()
    # OCR sometimes turns dashed separators into lots of '-' or '='
    return len(t) >= 6 and all(ch in "-_=—" for ch in t)


def _is_totalish(line: str) -> bool:
    t = (line or "").strip().upper()
    return any(k in t for k in ["SUB TOTAL", "SUBTOTAL", "TOTAL", "TAX"])


def _slice_item_region(lines: List[str]) -> List[str]:
    """
    Heuristics:
      - Prefer region after obvious header markers (REGISTER/ORDER/RECEIPT/DATE)
      - Start at first "item-looking" line
      - End at totals/payment footer markers
    """
    up = [ln.strip() for ln in lines if ln and ln.strip()]
    if not up:
        return []

    # 1) choose a reasonable start anchor (after header)
    start = 0
    for i, ln in enumerate(up[:25]):
        # Header anchor: use strong header fields. Special-case DAISO "SALES" line,
        # but do NOT treat "SALES TAX" as a header anchor (it appears in the footer).
        if (_REGISTER_W.search(ln) or _ORDER_W.search(ln) or _RECEIPT_W.search(ln)
                or _DATE_W.search(ln) or _TIME_W.search(ln)
                or _CASHIER_W.search(ln) or ln.strip().upper() == "SALES"):
            start = i + 1

    # 2) from that point, find first line that looks like an item
    for i in range(start, len(up)):
        if _looks_like_item_line(up[i]):
            start = i
            break

    # 3) find end at first footer marker AFTER we started
    end = len(up)
    for i in range(start, len(up)):
        if _is_footer_marker(up[i]):
            end = i
            break

    region = up[start:end]

    # remove totalish lines inside region (extra safety)
    region = [ln for ln in region if not _is_totalish(ln)]
    return region


def _classify_line_for_debug(line: str) -> dict:
    t = (line or "").strip()
    return {
        "line": t,
        "looks_like_item": _looks_like_item_line(t),
        "is_totalish": _is_totalish(t),
        "is_separator": _is_separator_line(t),
        "is_legend": _is_legend_line(t),
        "is_footer_marker": _is_footer_marker(t),
        "money_at_end": bool(_MONEY_AT_END_RE.search(t)),
        "qty_at_price": bool(_QTY_AT_PRICE_RE.match(t)),
        "money_only": bool(_MONEY_LINE_RE.match(t)),
    }


def slice_item_region_debug(lines: List[str]) -> dict:
    start = 0
    end = len(lines)

    debug = {
        "header_anchor_hit": None,
        "first_itemlike_hit": None,
        "footer_hit": None,
        "start_idx": None,
        "end_idx": None,
    }

    for i, line in enumerate(lines[:25]):
        u = (line or "").upper()
        # Use word-boundary checks so OCR like "Dateline" doesn't trigger "DATE".
        if (re.search(r"\bPAYMENT\b", u) or re.search(r"\bDATE\b", u) or re.search(r"\bTIME\b", u)
                or re.search(r"\bRECEIPT\b", u) or re.search(r"\bREGISTER\b", u)
                or re.search(r"\bCASHIER\b", u) or re.search(r"\bORDER\b", u)):
            start = i + 1
            debug["header_anchor_hit"] = {"idx": i, "line": line}
        if debug["first_itemlike_hit"] is None and _looks_like_item_line(line):
            debug["first_itemlike_hit"] = {"idx": i, "line": line}

    for j in range(start, len(lines)):
        if _is_footer_marker(lines[j]):
            end = j
            debug["footer_hit"] = {"idx": j, "line": lines[j]}
            break

    debug["start_idx"] = start
    debug["end_idx"] = end

    lo = max(0, start - 10)
    hi = min(len(lines), end + 10)
    debug["window"] = [_classify_line_for_debug(lines[k]) for k in range(lo, hi)]
    debug["sliced_lines"] = lines[start:end]
    return debug


def parse_items_from_lines(lines: List[str]) -> List[Dict[str, Any]]:
    region = _slice_item_region(lines)

    items: List[Dict[str, Any]] = []
    last_item_idx: Optional[int] = None

    prev_desc_candidate: Optional[str] = None  # last plain description (for metadata lines)

    pending_sku_item: bool = False  # Daiso-style: SKU line has price, next line is the real description

    def new_item(desc: str) -> None:
        nonlocal last_item_idx
        items.append({"name": desc.strip(), "price": None, "meta": [], "raw_line": desc})
        last_item_idx = len(items) - 1

    def attach_price(p: float, raw: str) -> None:
        if last_item_idx is None:
            return
        items[last_item_idx]["price"] = p
        items[last_item_idx]["meta"].append(raw.strip())

    def attach_meta(raw: str) -> None:
        if last_item_idx is None:
            return
        items[last_item_idx]["meta"].append(raw.strip())

    for ln in region:
        t = ln.strip()
        if not t:
            continue
        if _is_separator_line(t):
            continue
        if _is_legend_line(t):
            break

        # skip obvious headers
        if any(k in t.upper() for k in ["PAYMENT METHOD", "RECEIPT", "DATE TIME", "CASHIER", "CARD TYPE", "SALES"]):
            continue

        # Ignore explicit tax lines inside item region (prevents "TAX 0.50" becoming an item)
        if re.match(r"^\s*TAX\b", t, re.I):
            continue

        # --- metadata line (like ** GROCERY (F) $ 6.99)
        if _is_metadata_line(t):
            # NEW: if we haven't created an item yet, use the previous description line
            if last_item_idx is None and prev_desc_candidate:
                new_item(_clean_item_name(prev_desc_candidate))
                prev_desc_candidate = None

            attach_meta(_clean_meta_tag(t))
            val = _extract_price_loose(t)
            if val is not None:
                attach_price(val, f"price_from: {t}")
            continue

        # price-only line
        if _MONEY_LINE_RE.match(t):
            val = _normalize_money_to_float(t)
            if val is not None:
                attach_price(val, t)
            continue

        # If previous line was a SKU+price line (DAISO), and this line is a plain description,
        # treat this as the "real" item name (do not create a new item).
        if pending_sku_item and last_item_idx is not None:
            if (not _is_metadata_line(t)) and (not _is_totalish(t)) and (not _is_footer_marker(t)) and (
            not _is_separator_line(t)):
                # must NOT itself contain money / qty@price / another SKU
                contains_money = (_extract_price_loose(t) is not None) or bool(_MONEY_LINE_RE.match(t)) or bool(
                    _QTY_AT_PRICE_RE.match(t))
                looks_like_sku = bool(re.match(r"^\s*\d{7,14}\b", t))
                if (not contains_money) and (not looks_like_sku):
                    cleaned = _clean_item_name(t)
                    if cleaned:
                        # Replace abbreviated name from the SKU line with the clearer continuation line.
                        items[last_item_idx]["name"] = cleaned.strip()
                        items[last_item_idx]["raw_line"] = (items[last_item_idx]["raw_line"] + " | " + t).strip()
                    pending_sku_item = False
                    continue
            # If it doesn't qualify as a continuation, just clear the flag and continue normal parsing.
            pending_sku_item = False

        # SKU + inline price at end (DAISO-style): "4968988075990 Frosted gl 2.25"
        msku = re.match(r"^\s*(\d{7,14})\s+(.+?)\s*$", t)
        if msku:
            val = _extract_price_loose(t)
            if val is not None and (not _is_totalish(t)) and (not _is_footer_marker(t)):
                desc_part = msku.group(2)
                # strip the trailing price token from the description part
                desc_part = re.sub(r"\s+[$€£]?\s*\d{1,5}[.,]\d{2}\s*$", "", desc_part).strip()
                cleaned_desc = _clean_item_name(desc_part)
                if cleaned_desc:
                    new_item(cleaned_desc)
                    attach_price(val, f"price_from: {t}")
                    pending_sku_item = True
                    continue
        # Continuation line (DAISO-style): second line is a description with no price; append to previous item.
        # IMPORTANT: only do this when the priced line was a DAISO-style SKU+price line (meta has "price_from: <digits>").
        if last_item_idx is not None:
            has_price = isinstance(items[last_item_idx].get("price"), (int, float))
            looks_like_sku = bool(re.match(r"^\s*\d{7,14}\b", t))

            has_money = (
                    (_extract_price_loose(t) is not None)
                    or bool(_MONEY_LINE_RE.match(t))
                    or bool(_QTY_AT_PRICE_RE.match(t))
            )

            cur_meta_list = items[last_item_idx].get("meta") or []
            sku_priced = any(
                re.search(r"price_from:\s*\d{7,14}\b", str(mm), flags=re.I) for mm in cur_meta_list
            )

            if sku_priced and has_price and (not looks_like_sku) and (not has_money) and (
            not _is_footer_marker(t)) and (not _is_metadata_line(t)):
                items[last_item_idx]["name"] = _clean_item_name(items[last_item_idx]["name"] + " " + t)
                items[last_item_idx]["raw_line"] = (items[last_item_idx]["raw_line"] + " | " + t).strip()
                continue

        # otherwise: treat as description, but also remember it in case the next line is "GROCERY (F)"
        prev_desc_candidate = t
        new_item(_clean_item_name(t))

    # --- Post-pass merge for DAISO-style two-line items:
    # If we created an item from a SKU+price line, and the very next parsed "item"
    # has no price (plain description line), merge it into the priced item.
    i = 0
    while i < len(items) - 1:
        cur = items[i]
        nxt = items[i + 1]

        cur_price = cur.get("price")
        nxt_price = nxt.get("price")

        def _has_moneyish(s: str) -> bool:
            return (_extract_price_loose(s) is not None) or bool(_MONEY_LINE_RE.match(s)) or bool(
                _QTY_AT_PRICE_RE.match(s))

        cur_meta = " ".join(cur.get("meta") or []).upper()
        # only do this when the price came from a SKU line
        cur_is_sku_priced = "PRICE_FROM:" in cur_meta

        if cur_is_sku_priced and isinstance(cur_price, (int, float)) and (nxt_price is None):
            nxt_name = (nxt.get("name") or "").strip()
            nxt_raw = (nxt.get("raw_line") or "").strip()

            # next line must look like a plain description (no money, no SKU)
            looks_like_sku = bool(re.match(r"^\s*\d{7,14}\b", nxt_raw))
            if nxt_name and (not looks_like_sku) and (not _has_moneyish(nxt_raw)) and (not _is_totalish(nxt_raw)) and (
            not _is_footer_marker(nxt_raw)) and (not _is_metadata_line(nxt_raw)):
                # Replace abbreviated name with the clearer continuation line
                cur["name"] = _clean_item_name(nxt_name) or nxt_name
                cur["raw_line"] = (str(cur.get("raw_line") or "").strip() + " | " + nxt_raw).strip()
                # merge meta (rarely used here, but safe)
                if nxt.get("meta"):
                    cur["meta"] = (cur.get("meta") or []) + list(nxt.get("meta") or [])
                # drop the next item
                items.pop(i + 1)
                continue

        i += 1

    # --- Subtotal-based price correction (helps HMART-style receipts where OCR confuses the leading digit, e.g. "2.49" -> "7 49") ---
    subtotal = None
    for ln in lines:
        u = ln.upper()
        if ("SUBTOTAL" in u) or ("SUB TOTAL" in u):
            subtotal = _extract_price_loose(ln)
            if subtotal is None:
                msub = re.search(r"(\d{1,3})\s*[\.,\s]\s*(\d{2})\s*$", ln)
                if msub:
                    try:
                        subtotal = float(f"{int(msub.group(1))}.{msub.group(2)}")
                    except Exception:
                        subtotal = None
            break

    if subtotal is not None and items:
        priced = [it for it in items if isinstance(it.get("price"), (int, float))]
        if len(priced) == len(items) and len(items) >= 2:
            s = round(sum(float(it["price"]) for it in items), 2)
            if abs(s - float(subtotal)) >= 0.02:
                # Try fixing exactly one item's dollars while keeping the cents the same, to make the sum match subtotal.
                # IMPORTANT: iterate in a "most likely OCR mistake first" order. HMART often has prices like "7 49" where
                # the leading digit is misread (e.g., 2 -> 7), so we prefer correcting prices sourced from "weak" patterns.
                def _price_from_text(_it: dict) -> str:
                    for _m in _it.get("meta", []) or []:
                        if isinstance(_m, str) and _m.startswith("price_from:"):
                            return _m.split("price_from:", 1)[1].strip()
                    return ""

                def _weak_price_source(_txt: str) -> bool:
                    if not _txt:
                        return False
                    # spaced cents pattern: "7 49", "7  49"
                    if re.search(r"\b\d\s+\d{2}\b", _txt):
                        return True
                    # no explicit decimal/comma in the price chunk (often OCR drops punctuation)
                    if ("." not in _txt and "," not in _txt) and re.search(r"\b\d{1,2}\s*\d{2}\b$", _txt):
                        return True
                    # common OCR noise around prices on HMART lines
                    if re.search(r"(tee|tcc|ttc|\$\$)", _txt, re.IGNORECASE):
                        return True
                    return False

                candidates = []
                for it in items:
                    p = float(it["price"])
                    cents = int(round((p - math.floor(p)) * 100.0)) % 100
                    other_sum = round(s - p, 2)
                    needed = round(float(subtotal) - other_sum, 2)

                    # needed must be non-negative and have same cents to be a plausible "single digit/char" OCR fix
                    if needed < 0:
                        continue
                    needed_cents = int(round((needed - math.floor(needed)) * 100.0)) % 100
                    if needed_cents != cents:
                        continue

                    # Don't make absurd jumps (keeps Costco/HMart safe)
                    if abs(needed - p) > 15:
                        continue

                    src = _price_from_text(it)
                    weak = _weak_price_source(src)
                    # Lower score is better. Prefer weak sources, then smaller edits.
                    score = (0 if weak else 10) + abs(needed - p)
                    candidates.append((score, it, p, needed))

                if candidates:
                    candidates.sort(key=lambda t: t[0])
                    score, it, p, needed = candidates[0]
                    it["meta"].append(f"price_corrected:{p:.2f}->{needed:.2f} using subtotal:{subtotal}")
                    it["price"] = needed

    return items