from __future__ import annotations

import os
import re
from typing import Any

import requests as _requests

NETDATA_URL = os.getenv("NETDATA_URL", "http://127.0.0.1:19999")


def _netdata_dim_value(chart: dict, dim: str) -> float | None:
    d = (chart.get("dimensions") or {}).get(dim)
    if not d:
        return None
    v = d.get("value")
    return float(v) if v is not None else None


def get_homelab_metrics() -> dict:
    try:
        r = _requests.get(f"{NETDATA_URL}/api/v1/allmetrics", params={"format": "json"}, timeout=5)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"error": f"Netdata unreachable: {type(e).__name__}"}

    out: dict[str, Any] = {}

    cpu = data.get("system.cpu")
    if cpu:
        idle = _netdata_dim_value(cpu, "idle") or 0.0
        out["cpuUsedPercent"] = round(max(0.0, 100.0 - idle), 1)

    ram = data.get("system.ram")
    if ram:
        used = _netdata_dim_value(ram, "used") or 0.0
        free = _netdata_dim_value(ram, "free") or 0.0
        cached = _netdata_dim_value(ram, "cached") or 0.0
        buffers = _netdata_dim_value(ram, "buffers") or 0.0
        total = used + free + cached + buffers
        out["ram"] = {
            "usedMB": round(used, 1),
            "totalMB": round(total, 1),
            "usedPercent": round((used / total * 100.0), 1) if total else None,
        }

    root_disk = data.get("disk_space./")
    if root_disk:
        used = _netdata_dim_value(root_disk, "used") or 0.0
        avail = _netdata_dim_value(root_disk, "avail") or 0.0
        total = used + avail
        out["diskRoot"] = {
            "usedGB": round(used, 1),
            "totalGB": round(total, 1),
            "usedPercent": round((used / total * 100.0), 1) if total else None,
        }

    net = data.get("system.net")
    if net:
        out["network"] = {
            "inKbps": _netdata_dim_value(net, "InOctets"),
            "outKbps": _netdata_dim_value(net, "OutOctets"),
            "units": net.get("units"),
        }

    temps = []
    for key, chart in data.items():
        if key.startswith("sensors.temperature_") and key.endswith("_input"):
            val = _netdata_dim_value(chart, "input")
            if val is None:
                continue
            # Chart "name" fields are often identical to the raw key on this
            # sensors plugin, so build a short human label from the key itself,
            # e.g. "sensors.temperature_coretemp-isa-0000_temp2_Core_0_input"
            # -> "coretemp Core 0", "sensors.temperature_pch_cometlake-virtual-0_temp1_input"
            # -> "pch cometlake temp1".
            raw = key[len("sensors.temperature_"):-len("_input")]
            chip = raw.split("-", 1)[0].replace("_", " ")
            m = re.search(r"_(temp\d+)_?(.*)$", raw)
            suffix = (m.group(2) if m else "").replace("_", " ").strip()
            temp_id = m.group(1) if m else ""
            label = f"{chip} {suffix}".strip() if suffix else f"{chip} {temp_id}".strip()
            temps.append({"label": label or raw, "celsius": round(val, 1)})
    if temps:
        out["temperatures"] = temps

    return out
