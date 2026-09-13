from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException

from app.db import database as db
from app.services import pollers

router = APIRouter()


# ── Realtime snapshots ──────────────────────────────────


@router.get("/health")
async def health():
    return {"status": "up"}


@router.get("/device-status")
async def device_status(device: str | None = Query(None)):
    return await db.query_device_status(device)


@router.get("/realtime/pressure")
async def realtime_pressure():
    return {
        "devices": pollers.latest_pressure,
        "time": db.now_str(),
    }


@router.get("/realtime/water")
async def realtime_water(device: str | None = Query(None)):
    if device:
        snap = pollers.latest_fy600_devices.get(device)
        if not snap:
            raise HTTPException(404, f"FY600 device not found: {device}")
        return {**snap, "time": db.now_str()}
    return {"devices": pollers.latest_fy600_devices, "time": db.now_str()}


@router.get("/fy600")
async def fy600_compat():
    """Backward-compatible snapshot for older clients."""
    w = pollers.latest_water
    return {
        "pv": w["level"],
        "sv": w["setpoint"],
        "output": w["output"],
        "status": w["status"],
    }


# ── History (frontend contract) ─────────────────────────


@router.get("/pressure/database/filter")
async def pressure_filter(
    start: str = Query(..., description="YYYY-MM-DD HH:MM:SS"),
    end: str = Query(..., description="YYYY-MM-DD HH:MM:SS"),
    device: str | None = Query(None),
):
    _validate_range(start, end)
    rows = await db.query_pressure(start, end, device=device)
    return rows


@router.get("/water-tank/database/filter")
async def water_filter(
    start: str = Query(..., description="YYYY-MM-DD HH:MM:SS"),
    end: str = Query(..., description="YYYY-MM-DD HH:MM:SS"),
    device: str | None = Query(None),
):
    _validate_range(start, end)
    # Frontend expects { device, value, time } — value = level
    return await db.query_water(start, end, device=device)


@router.get("/water-tank/database/filter/full")
async def water_filter_full(
    start: str = Query(...),
    end: str = Query(...),
    device: str | None = Query(None),
):
    _validate_range(start, end)
    return await db.query_water_full(start, end, device=device)


# ── Aliases matching old Flask paths (optional) ─────────


@router.get("/modbus/database/filter")
async def modbus_filter_alias(
    start: str = Query(...), end: str = Query(...), device: str | None = Query(None)
):
    _validate_range(start, end)
    return await db.query_pressure(start, end, device=device)


@router.get("/fy600/database/filter")
async def fy600_filter_alias(
    start: str = Query(...), end: str = Query(...), device: str | None = Query(None)
):
    _validate_range(start, end)
    return await db.query_water(start, end, device=device)


# ── Ops ─────────────────────────────────────────────────


@router.get("/stats")
async def stats():
    return await db.db_stats()


@router.post("/admin/cleanup")
async def force_cleanup():
    return await db.cleanup_old_data()


def _validate_range(start: str, end: str) -> None:
    if len(start) < 16 or len(end) < 16:
        raise HTTPException(400, "Invalid datetime format. Use YYYY-MM-DD HH:MM:SS")
    if end < start:
        raise HTTPException(400, "end must be after start")
