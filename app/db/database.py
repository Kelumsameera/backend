"""
SQLite (WAL) storage optimised for time-series on a mini-PC.

Design choices to avoid slowdown / disk fill:
- WAL mode → concurrent readers while writer runs
- Indexed (device, time) → fast range queries
- Automatic retention DELETE (no unbounded growth)
- INSERT in batches / single-row with small transaction
- History queries always LIMIT-capped
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from app.config import settings

# Asia/Colombo fixed offset (no pytz dependency)
COLOMBO = timezone(timedelta(hours=5, minutes=30))

_db: aiosqlite.Connection | None = None


def now_colombo() -> datetime:
    return datetime.now(COLOMBO)


def now_str() -> str:
    return now_colombo().strftime("%Y-%m-%d %H:%M:%S")


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        path = Path(settings.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(path))
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA synchronous=NORMAL")
        await _db.execute("PRAGMA temp_store=MEMORY")
        await _db.execute("PRAGMA cache_size=-8000")  # ~8 MB page cache
        await _db.execute("PRAGMA busy_timeout=5000")
        await _init_schema(_db)
    return _db


async def _init_schema(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS pressure_readings (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            device  TEXT    NOT NULL,
            value   REAL    NOT NULL,
            time    TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pressure_time
            ON pressure_readings (time);
        CREATE INDEX IF NOT EXISTS idx_pressure_device_time
            ON pressure_readings (device, time);

        CREATE TABLE IF NOT EXISTS water_readings (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            device  TEXT    NOT NULL DEFAULT 'fy600',
            level   REAL    NOT NULL,
            setpoint REAL   NOT NULL,
            output  REAL    NOT NULL,
            time    TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_water_time
            ON water_readings (time);
        CREATE INDEX IF NOT EXISTS idx_water_device_time
            ON water_readings (device, time);

        CREATE TABLE IF NOT EXISTS device_status (
            device          TEXT NOT NULL,
            tank_id         TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'OFFLINE',
            last_seen       TEXT,
            last_error      TEXT,
            updated_at      TEXT NOT NULL,
            PRIMARY KEY (device)
        );

        -- Lightweight 1-min downsampled averages (optional long-term)
        CREATE TABLE IF NOT EXISTS pressure_1min (
            device  TEXT NOT NULL,
            avg_val REAL NOT NULL,
            bucket  TEXT NOT NULL,
            PRIMARY KEY (device, bucket)
        );
        """)
    await db.commit()


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


# ── Writes ──────────────────────────────────────────────


async def insert_pressure(device: str, value: float, ts: str | None = None) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO pressure_readings (device, value, time) VALUES (?, ?, ?)",
        (device, value, ts or now_str()),
    )
    await db.commit()


async def insert_water(
    level: float,
    setpoint: float,
    output: float,
    device: str = "fy600",
    ts: str | None = None,
) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO water_readings (device, level, setpoint, output, time) VALUES (?, ?, ?, ?, ?)",
        (device, level, setpoint, output, ts or now_str()),
    )
    await db.commit()


async def upsert_device_status(
    device: str,
    tank_id: str,
    status: str,
    last_seen: str | None = None,
    last_error: str | None = None,
) -> None:
    db = await get_db()
    ts = last_seen or now_str()
    await db.execute(
        """
        INSERT INTO device_status (device, tank_id, status, last_seen, last_error, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(device) DO UPDATE SET
            tank_id=excluded.tank_id,
            status=excluded.status,
            last_seen=excluded.last_seen,
            last_error=excluded.last_error,
            updated_at=excluded.updated_at
        """,
        (device, tank_id, status, ts, last_error, ts),
    )
    await db.commit()


async def query_device_status(device: str | None = None) -> list[dict[str, Any]]:
    db = await get_db()
    if device:
        cur = await db.execute(
            "SELECT device, tank_id, status, last_seen, last_error, updated_at FROM device_status WHERE device = ? ORDER BY updated_at DESC",
            (device,),
        )
    else:
        cur = await db.execute(
            "SELECT device, tank_id, status, last_seen, last_error, updated_at FROM device_status ORDER BY updated_at DESC"
        )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Reads ───────────────────────────────────────────────


async def query_pressure(
    start: str,
    end: str,
    limit: int | None = None,
    device: str | None = None,
) -> list[dict[str, Any]]:
    limit = min(limit or settings.history_max_rows, settings.history_max_rows)
    db = await get_db()
    if device:
        cur = await db.execute(
            """
            SELECT device, value, time
            FROM pressure_readings
            WHERE time >= ? AND time <= ? AND device = ?
            ORDER BY time ASC
            LIMIT ?
            """,
            (start, end, device, limit),
        )
    else:
        cur = await db.execute(
            """
            SELECT device, value, time
            FROM pressure_readings
            WHERE time >= ? AND time <= ?
            ORDER BY time ASC
            LIMIT ?
            """,
            (start, end, limit),
        )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def query_water(
    start: str,
    end: str,
    limit: int | None = None,
    device: str | None = None,
) -> list[dict[str, Any]]:
    """Return rows shaped as {device, value, time} using level as value (frontend contract)."""
    limit = min(limit or settings.history_max_rows, settings.history_max_rows)
    db = await get_db()
    if device:
        cur = await db.execute(
            """
            SELECT device, level AS value, time
            FROM water_readings
            WHERE time >= ? AND time <= ? AND device = ?
            ORDER BY time ASC
            LIMIT ?
            """,
            (start, end, device, limit),
        )
    else:
        cur = await db.execute(
            """
            SELECT device, level AS value, time
            FROM water_readings
            WHERE time >= ? AND time <= ?
            ORDER BY time ASC
            LIMIT ?
            """,
            (start, end, limit),
        )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def query_water_full(
    start: str,
    end: str,
    limit: int | None = None,
    device: str | None = None,
) -> list[dict[str, Any]]:
    limit = min(limit or settings.history_max_rows, settings.history_max_rows)
    db = await get_db()
    if device:
        cur = await db.execute(
            """
            SELECT device, level, setpoint, output, time
            FROM water_readings
            WHERE time >= ? AND time <= ? AND device = ?
            ORDER BY time ASC
            LIMIT ?
            """,
            (start, end, device, limit),
        )
    else:
        cur = await db.execute(
            """
            SELECT device, level, setpoint, output, time
            FROM water_readings
            WHERE time >= ? AND time <= ?
            ORDER BY time ASC
            LIMIT ?
            """,
            (start, end, limit),
        )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Retention / maintenance ─────────────────────────────


async def cleanup_old_data() -> dict[str, int | str]:
    """Delete rows older than retention_days. Keeps disk under control."""
    cutoff = (now_colombo() - timedelta(days=settings.retention_days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    db = await get_db()
    cur1 = await db.execute("DELETE FROM pressure_readings WHERE time < ?", (cutoff,))
    cur2 = await db.execute("DELETE FROM water_readings WHERE time < ?", (cutoff,))
    await db.commit()
    # Reclaim space occasionally
    await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return {
        "pressure_deleted": cur1.rowcount,
        "water_deleted": cur2.rowcount,
        "cutoff": cutoff,
    }


async def db_stats() -> dict[str, Any]:
    db = await get_db()
    path = Path(settings.database_path)
    size_mb = path.stat().st_size / (1024 * 1024) if path.exists() else 0

    async def count(table: str) -> int:
        cur = await db.execute(f"SELECT COUNT(*) FROM {table}")
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    return {
        "pressure_rows": await count("pressure_readings"),
        "water_rows": await count("water_readings"),
        "device_status_rows": await count("device_status"),
        "db_size_mb": round(size_mb, 2),
        "retention_days": settings.retention_days,
        "path": str(path.resolve()),
    }
