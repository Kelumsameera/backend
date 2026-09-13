# Flexicare Monitoring Backend v2

High-efficiency Python backend for factory pressure gauges + water tank level.

## Why this design (no slowdown / no disk fill)

| Concern | Solution |
| ------- | -------- |
| Memory | FastAPI + async Socket.IO (no Flask-eventlet, no InfluxDB JVM) |
| Disk growth | SQLite WAL + **automatic retention** (default 14 days) |
| CPU | Single async event loop, poll interval 2 s, connection per read |
| Query load | Indexed time columns + hard `LIMIT` on history APIs |
| Reliability | Open/close Modbus per cycle (survives gateway reboots) |

Estimated storage: ~2 s poll × 3 signals ≈ **130k rows/day**.  
14-day retention ≈ **~50–80 MB** SQLite file — stays small forever.

## Frontend contract (matches TSX app)

### Socket.IO events

```json
// Pressure
{ "device": "production_clean_room" | "assembly_clean_room", "value": 12.5 }

// Water tank
{ "level": 145.0, "setpoint": 180.0, "output": 65.0 }
```

### REST

```text
GET /pressure/database/filter?start=YYYY-MM-DD HH:mm:ss&end=...
GET /water-tank/database/filter?start=...&end=...
GET /realtime/pressure
GET /realtime/water
GET /stats
POST /admin/cleanup
GET /health
```

## Quick start (mini-PC)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit Modbus IPs if needed

mkdir -p data
python -m uvicorn app.main:app --host 0.0.0.0 --port 3000
```

Or with Docker:

```bash
cp .env.example .env
docker compose up -d --build
```

Point the frontend:

```text
NEXT_PUBLIC_SOCKET_URL=http://<mini-pc-ip>:3000
NEXT_PUBLIC_API_URL=http://<mini-pc-ip>:3000
```

## Config (`.env`)

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `PRESSURE_*_IP` | 192.168.0.7 / .17 | Pressure gateway IPs |
| `FY600_IP` | 192.168.0.16 | Water tank controller |
| `*_POLL_INTERVAL` | 2.0 | Seconds between reads |
| `RETENTION_DAYS` | 14 | Auto-delete older raw data |
| `HISTORY_MAX_ROWS` | 5000 | Cap on API responses |
| `DATABASE_PATH` | `./data/modbus.db` | SQLite file |

## Ops

```bash
# Live stats (row counts + DB size)
curl http://localhost:3000/stats

# Force retention cleanup now
curl -X POST http://localhost:3000/admin/cleanup
```

Cleanup also runs automatically every `CLEANUP_INTERVAL_HOURS` (default 6 h).

## Project layout

```text
app/
  main.py           # FastAPI + Socket.IO ASGI app
  config.py         # pydantic-settings
  api/routes.py     # REST endpoints
  db/database.py    # SQLite WAL + retention
  modbus/client.py  # Async Modbus TCP helpers
  services/pollers.py
```
