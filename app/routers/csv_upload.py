from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()

SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _safe_target_filename(name: str) -> str:
    """
    Enforce a simple safe filename rule; also force .csv extension.
    """
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing target name")
    if not SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid target name: {name}")
    if not name.lower().endswith(".csv"):
        name = f"{name}.csv"
    return name


@router.post("/csv/ingest")
async def ingest_csvs(
    target_names: List[str] = Form(...),
    files: List[UploadFile] = File(...),
):
    if len(target_names) != len(files):
        raise HTTPException(status_code=400, detail="target_names/files length mismatch")

    # repo_root = .../webApp
    repo_root = Path(__file__).resolve().parents[2]

    script_path = repo_root / "emails" / "postedDownload.py"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"Missing script: {script_path}")

    temp_dir = Path(tempfile.mkdtemp(prefix="csv_ingest_"))
    saved_paths: List[Path] = []

    try:
        # Save each upload into temp_dir using the user-provided *target* name
        for target, uf in zip(target_names, files):
            target_fname = _safe_target_filename(target)
            out_path = temp_dir / target_fname

            # Stream-write upload to disk
            try:
                with out_path.open("wb") as f:
                    while True:
                        chunk = await uf.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
            finally:
                try:
                    await uf.close()
                except Exception:
                    pass

            saved_paths.append(out_path)

        # Run your importer against the temp dir
        cmd = [sys.executable, str(script_path), "--input-dir", str(temp_dir)]
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )

        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "postedDownload.py failed",
                    "returncode": proc.returncode,
                    "processed": [p.name for p in saved_paths],
                    "stdout": (proc.stdout or "")[-4000:],
                    "stderr": (proc.stderr or "")[-4000:],
                },
            )

        return JSONResponse(
            {
                "ok": True,
                "processed": [p.name for p in saved_paths],
                "stdout": (proc.stdout or "")[-4000:],
                "stderr": (proc.stderr or "")[-4000:],
            }
        )

    finally:
        # Always delete temp workspace so nothing is stored permanently
        shutil.rmtree(temp_dir, ignore_errors=True)
