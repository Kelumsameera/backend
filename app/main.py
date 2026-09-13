"""
Flexicare Monitoring Backend
────────────────────────────
FastAPI + python-socketio (async) + SQLite WAL

Designed for mini-PC:
  • Low memory (no InfluxDB JVM, no eventlet monkey-patch)
  • Disk-safe (retention policy + WAL checkpoint)
  • Non-blocking Modbus polls
  • Exact Socket.IO / REST contract for the TSX frontend
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
from app.db import database as db
from app.services import pollers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")

# ── Socket.IO (async) ───────────────────────────────────
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
    # Keep memory low: no large message buffers
    max_http_buffer_size=1_000_000,
)


async def emit(event: str, data: dict) -> None:
    await sio.emit(event, data)


@sio.event
async def connect(sid, environ):
    log.info("Client connected: %s", sid)
    # Push latest pressure snapshot immediately
    await sio.emit(
        "modbus_update",
        {
            "device": "production_clean_room",
            "value": pollers.latest_pressure["production_clean_room"],
        },
        to=sid,
    )
    await sio.emit(
        "modbus_update",
        {
            "device": "assembly_clean_room",
            "value": pollers.latest_pressure["assembly_clean_room"],
        },
        to=sid,
    )

    # Push latest FY600 snapshot immediately, one event per configured device.
    # This preserves the existing frontend contract while adding device/tank identity.
    for device, row in pollers.latest_fy600_devices.items():
        await sio.emit(
            "water_tank_update",
            {
                "device": device,
                "tank_id": row.get("tank_id", device),
                "level": row.get("level", 0.0),
                "setpoint": row.get("setpoint", 0.0),
                "output": row.get("output", 0.0),
                "status": row.get("status", "OFFLINE"),
                "time": row.get("time", db.now_str()),
            },
            to=sid,
        )

    if not pollers.latest_fy600_devices:
        await sio.emit(
            "water_tank_update",
            {
                "device": "fy600",
                "tank_id": "fy600",
                "level": pollers.latest_water["level"],
                "setpoint": pollers.latest_water["setpoint"],
                "output": pollers.latest_water["output"],
                "status": pollers.latest_water["status"],
                "time": db.now_str(),
            },
            to=sid,
        )


@sio.event
async def disconnect(sid):
    log.info("Client disconnected: %s", sid)


# ── Lifespan ────────────────────────────────────────────
_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting backend…")
    await db.get_db()

    _tasks.append(asyncio.create_task(pollers.pressure_loop(emit)))
    _tasks.append(asyncio.create_task(pollers.water_loop(emit)))
    _tasks.append(asyncio.create_task(pollers.cleanup_loop()))

    log.info(
        "Pollers running | pressure every %.1fs | water every %.1fs | retention %dd",
        settings.pressure_poll_interval,
        settings.fy600_poll_interval,
        settings.retention_days,
    )
    yield

    log.info("Shutting down…")
    for t in _tasks:
        t.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    await db.close_db()


# ── FastAPI app ─────────────────────────────────────────
fastapi_app = FastAPI(
    title="Flexicare Monitoring API",
    version="2.0.0",
    lifespan=lifespan,
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(router)

# Mount Socket.IO on the same port
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        # Single worker is correct for in-process pollers + shared state
        workers=1,
    )
