"""
Background async pollers.

- One task per logical device group
- Bounded in-memory state (latest values only)
- Persist every successful read
- Emit Socket.IO events matching the TSX frontend contract
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Awaitable

from app.config import settings
from app.db import database as db
from app.modbus import client as modbus

log = logging.getLogger("pollers")

# Latest values kept in RAM (tiny footprint)
latest_pressure: dict[str, float] = {
    "production_clean_room": 0.0,
    "assembly_clean_room": 0.0,
}
latest_water: dict[str, Any] = {
    "level": 0.0,
    "setpoint": 0.0,
    "output": 0.0,
    "status": "disconnected",
}
latest_fy600_devices: dict[str, dict[str, Any]] = {}

EmitFn = Callable[[str, dict], Awaitable[None] | None]


async def pressure_loop(emit: EmitFn) -> None:
    devices = [
        {
            "name": "production_clean_room",
            "ip": settings.pressure_production_ip,
            "unit": settings.pressure_production_unit,
        },
        {
            "name": "assembly_clean_room",
            "ip": settings.pressure_assembly_ip,
            "unit": settings.pressure_assembly_unit,
        },
    ]

    while True:
        for d in devices:
            try:
                value = await modbus.read_float32(
                    host=d["ip"],
                    port=settings.pressure_port,
                    unit=d["unit"],
                    address=settings.pressure_register,
                )
                if value is None:
                    continue

                latest_pressure[d["name"]] = value
                ts = db.now_str()

                await db.insert_pressure(d["name"], value, ts)

                result = emit(
                    "modbus_update",
                    {"device": d["name"], "value": value, "time": ts},
                )
                if asyncio.iscoroutine(result):
                    await result

            except Exception as e:
                log.error("Pressure poll %s: %s", d["name"], e)

        await asyncio.sleep(settings.pressure_poll_interval)


async def water_loop(emit: EmitFn) -> None:
    """
    FY600 registers are loaded from the configuration registry. Existing
    register map comments are retained as REQUIRES CONFIRMATION for any
    unknown/unverified address semantics.
    """
    devices = settings.fy600_devices or [
        {
            "name": "fy600",
            "tank_id": "fy600",
            "ip": settings.fy600_ip,
            "port": settings.fy600_port,
            "unit": settings.fy600_unit,
            "level_register": 0x008A,
            "setpoint_register": 0x0000,
            "output_register": 0x0087,
            "level_scale": 1.0,
            "setpoint_scale": 10.0,
            "output_scale": 10.0,
            "timeout": 2.0,
            "retries": 2,
            "retry_delay": 0.2,
            "reconnect_delay": 3.0,
            "stale_after_seconds": 30,
            "enabled": True,
        }
    ]

    # Track device-specific loops by task in a singleton scheduler form
    for cfg in devices:
        if not cfg.get("enabled", True):
            continue
        asyncio.create_task(_poll_single_fy600(cfg, emit))

    # Keep the legacy single-device snapshot object updated
    await asyncio.sleep(settings.fy600_poll_interval)
    while True:
        try:
            if latest_fy600_devices:
                first = next(iter(latest_fy600_devices.values()))
                latest_water.update(
                    {
                        "level": first.get("level", 0.0),
                        "setpoint": first.get("setpoint", 0.0),
                        "output": first.get("output", 0.0),
                        "status": first.get("status", "connected"),
                    }
                )
        except Exception:
            pass
        await asyncio.sleep(settings.fy600_poll_interval)


async def _poll_single_fy600(cfg: dict[str, Any], emit: EmitFn) -> None:
    """Poll one FY600 device independently and release the error so the next device loop continues.

    This keeps the existing backend architecture intact while enabling one-off
    device isolation. A failed device updates its health record and errors out
    without halting the remaining task list of device pollers.
    """
    device = cfg.get("name") or cfg.get("tank_id") or "fy600"
    tank_id = cfg.get("tank_id") or device
    host = cfg.get("ip") or settings.fy600_ip
    port = int(cfg.get("port") or settings.fy600_port)
    unit = int(cfg.get("unit") or settings.fy600_unit)
    timeout = float(cfg.get("timeout") or 2.0)
    retries = int(cfg.get("retries") or 2)
    retry_delay = float(cfg.get("retry_delay") or 0.2)
    reconnect_delay = float(cfg.get("reconnect_delay") or 3.0)
    stale_after_seconds = int(cfg.get("stale_after_seconds") or 30)

    while True:
        try:
            # Perform per-register reads with explicit retry isolation and
            # return the tuple of values per device; no cross-device coupling.
            level = await _read_with_retry(
                modbus.read_uint16_input,
                host,
                port,
                unit,
                int(cfg.get("level_register") or 0x008A),
                scale=float(cfg.get("level_scale") or 1.0),
                timeout=timeout,
                retries=retries,
                retry_delay=retry_delay,
            )
            setpoint = await _read_with_retry(
                modbus.read_uint16_holding,
                host,
                port,
                unit,
                int(cfg.get("setpoint_register") or 0x0000),
                scale=float(cfg.get("setpoint_scale") or 10.0),
                timeout=timeout,
                retries=retries,
                retry_delay=retry_delay,
            )
            output = await _read_with_retry(
                modbus.read_uint16_input,
                host,
                port,
                unit,
                int(cfg.get("output_register") or 0x0087),
                scale=float(cfg.get("output_scale") or 10.0),
                timeout=timeout,
                retries=retries,
                retry_delay=retry_delay,
            )

            if level is None and setpoint is None and output is None:
                status = "OFFLINE"
                latest_fy600_devices[device] = {
                    "device": device,
                    "tank_id": tank_id,
                    "level": latest_fy600_devices.get(device, {}).get("level", 0.0),
                    "setpoint": latest_fy600_devices.get(device, {}).get(
                        "setpoint", 0.0
                    ),
                    "output": latest_fy600_devices.get(device, {}).get("output", 0.0),
                    "status": status,
                    "time": db.now_str(),
                }
                await db.upsert_device_status(
                    device, tank_id, status, last_error="all registers unavailable"
                )
                await emit(
                    "water_tank_update",
                    {
                        "device": device,
                        "tank_id": tank_id,
                        "level": latest_fy600_devices[device]["level"],
                        "setpoint": latest_fy600_devices[device]["setpoint"],
                        "output": latest_fy600_devices[device]["output"],
                        "status": status,
                        "time": db.now_str(),
                    },
                )
                await asyncio.sleep(reconnect_delay)
                continue

            level = (
                level
                if level is not None
                else latest_fy600_devices.get(device, {}).get("level", 0.0)
            )
            setpoint = (
                setpoint
                if setpoint is not None
                else latest_fy600_devices.get(device, {}).get("setpoint", 0.0)
            )
            output = (
                output
                if output is not None
                else latest_fy600_devices.get(device, {}).get("output", 0.0)
            )

            status = "ONLINE"
            latest_fy600_devices[device] = {
                "device": device,
                "tank_id": tank_id,
                "level": level,
                "setpoint": setpoint,
                "output": output,
                "status": status,
                "time": db.now_str(),
            }
            ts = db.now_str()
            await db.insert_water(level, setpoint, output, device=device, ts=ts)
            await db.upsert_device_status(device, tank_id, status, last_seen=ts)

            result = emit(
                "water_tank_update",
                {
                    "device": device,
                    "tank_id": tank_id,
                    "level": level,
                    "setpoint": setpoint,
                    "output": output,
                    "status": status,
                    "time": ts,
                },
            )
            if asyncio.iscoroutine(result):
                await result

        except Exception as e:
            status = "ERROR"
            old = latest_fy600_devices.get(device, {})
            latest_fy600_devices[device] = {
                "device": device,
                "tank_id": tank_id,
                "level": old.get("level", 0.0),
                "setpoint": old.get("setpoint", 0.0),
                "output": old.get("output", 0.0),
                "status": status,
                "time": db.now_str(),
            }
            log.error("Water poll %s: %s", device, e)
            await db.upsert_device_status(device, tank_id, status, last_error=str(e))

        await asyncio.sleep(settings.fy600_poll_interval)


async def _read_with_retry(
    fn,
    host: str,
    port: int,
    unit: int,
    address: int,
    *,
    scale: float,
    timeout: float,
    retries: int,
    retry_delay: float,
):
    last = None
    for attempt in range(max(1, retries + 1)):
        try:
            if fn.__name__ == "read_uint16_input":
                last = await modbus.read_uint16_input(
                    host,
                    port,
                    unit,
                    address,
                    scale=scale,
                    timeout=timeout,
                )
            elif fn.__name__ == "read_uint16_holding":
                last = await modbus.read_uint16_holding(
                    host,
                    port,
                    unit,
                    address,
                    scale=scale,
                    timeout=timeout,
                )
            else:
                return None
            if last is not None:
                return last
        except Exception as e:
            log.warning("Retry %s/%s for %s: %s", attempt + 1, retries + 1, host, e)
        if attempt < retries:
            await asyncio.sleep(retry_delay)
    return last


async def cleanup_loop() -> None:
    interval = max(1.0, settings.cleanup_interval_hours) * 3600
    # First run after a short delay so app starts fast
    await asyncio.sleep(60)
    while True:
        try:
            stats = await db.cleanup_old_data()
            log.info("Retention cleanup: %s", stats)
        except Exception as e:
            log.error("Cleanup failed: %s", e)
        await asyncio.sleep(interval)
