# Flexicare Monitoring Backend v2

A FastAPI-based backend for collecting pressure-gauge and water-tank telemetry from Modbus-compatible devices and exposing the resulting data as realtime events and REST APIs.

## Overview

This service reads device data asynchronously, stores the readings in SQLite, and provides a small API surface for realtime dashboards, database history, statistics, and cleanup operations.

The design prioritizes a lightweight local deployment model:

- FastAPI for the HTTP and realtime API layer
- Async background polling for device reads
- SQLite for local persistence with automatic retention
- Simple REST endpoints for history and health monitoring

## Features

- Realtime pressure and water-tank telemetry
- Historian-style database queries
- Resource retention and cleanup controls
- Health and statistics endpoints
- Local `.env` configuration for device hosts and runtime settings

## Local development

Create and activate a virtual environment:

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy the sample environment file and update values locally:

```bash
cp .env.example .env
```

Create the local data directory, then start the app:

```bash
mkdir -p data
python -m uvicorn app.main:app --host 0.0.0.0 --port 3000
```

Or run with Docker:

```bash
docker compose up -d --build
```

## Environment configuration

Keep secrets and host-specific values in a local `.env` file. Do not commit the file to source control.

| Variable | Example | Meaning |
| ------- | ------- | ------- |
| `SENSOR_HOST_*` | `replace-with-device-host` | Device gateway or controller host |
| `POLL_INTERVAL_SECONDS` | `2.0` | Poll interval used by the backend |
| `RETENTION_DAYS` | `14` | Number of days to retain raw readings |
| `HISTORY_MAX_ROWS` | `5000` | Maximum rows returned by history APIs |
| `DATABASE_PATH` | `./data/modbus.db` | SQLite database path |
| `CLEANUP_INTERVAL_HOURS` | `6` | Automatic cleanup schedule |

## API overview

The backend exposes a small public API for dashboard integrations and operational checks.

### REST

```text
GET /health
GET /stats
GET /realtime/pressure
GET /realtime/water
GET /pressure/database/filter
GET /water-tank/database/filter
POST /admin/cleanup
```

### Realtime events

The service also emits realtime updates for pressure and water-tank topics through the Socket.IO event layer.

## Operations

Check server health and telemetry statistics locally:

```bash
curl http://localhost:3000/health
curl http://localhost:3000/stats
```

Run a cleanup manually:

```bash
curl -X POST http://localhost:3000/admin/cleanup
```

## Project structure

```text
app/
  main.py
  config.py
  api/routes.py
  db/database.py
  modbus/client.py
  services/pollers.py
```

Automatic deployment configured.
