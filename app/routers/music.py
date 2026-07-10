from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/music", tags=["music"])

MUSIC_MANAGER_URL = (os.getenv("MUSIC_MANAGER_URL", "") or "").strip().rstrip("/")
MUSIC_MANAGER_USERNAME = os.getenv("MUSIC_MANAGER_USERNAME", "")
MUSIC_MANAGER_PASSWORD = os.getenv("MUSIC_MANAGER_PASSWORD", "")


def _music_enabled() -> bool:
    return bool(MUSIC_MANAGER_URL)


def _require_music_enabled():
    if not _music_enabled():
        raise HTTPException(
            status_code=501,
            detail="Quail Music isn't configured on this server (MUSIC_MANAGER_URL unset) — "
            "this endpoint only runs on the homelab, not the hosted web app.",
        )


async def _mm_request(method: str, path: str, params: dict | None = None):
    _require_music_enabled()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.request(
            method,
            f"{MUSIC_MANAGER_URL}{path}",
            params=params or {},
            auth=(MUSIC_MANAGER_USERNAME, MUSIC_MANAGER_PASSWORD),
        )
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="Not found")
        r.raise_for_status()
        return r.json()


@router.get("/stats")
async def music_stats():
    return await _mm_request("GET", "/api/stats")


@router.get("/recommended")
async def music_recommended():
    return await _mm_request("GET", "/api/recommended")


@router.get("/search")
async def music_search(q: str = Query("")):
    return await _mm_request("GET", "/api/search", {"q": q})


@router.delete("/tracks/{item_id}")
async def music_delete_track(item_id: str):
    return await _mm_request("DELETE", f"/api/tracks/{item_id}")
