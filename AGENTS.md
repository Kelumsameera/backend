# AGENTS.md

This repository is the Flexicare Monitoring Backend v2: a FastAPI service that polls Modbus-compatible pressure gauges and FY600 water-tank devices, persists time-series data in SQLite, and exposes both REST and Socket.IO realtime endpoints.

## Primary sources of truth

- The user-facing project overview and local setup examples are in [README.md](README.md).
- Application runtime wiring starts in [app/main.py](app/main.py).
- HTTP routes and endpoint contracts live in [app/api/routes.py](app/api/routes.py).
- Polling and event emission logic lives in [app/services/pollers.py](app/services/pollers.py).
- Settings and defaults live in [app/config.py](app/config.py).
- SQLite schema and retention/query helpers live in [app/db/database.py](app/db/database.py).

## Architecture expectations

- Keep FastAPI endpoint logic in the router file and avoid adding ad-hoc routes beyond the existing route surface.
- Keep device polling loops in the service pollers module rather than mixing device I/O into route handlers.
- Preserve backward-compatible endpoints and emitted event names when extending the API.
- Keep time-series storage lightweight: SQLite WAL mode, bounded history queries, and retention cleanup are intentional.
- Treat configuration as environment-backed Pydantic settings loaded from `.env` by default. Keep host/device-specific values out of committed files.

## Coding conventions

- Favor small, typed async functions that fit the existing async FastAPI/Socket.IO pattern.
- Use the existing `settings` object from [app/config.py](app/config.py) for hostnames, ports, intervals, database paths, and device registries.
- For FY600 device registries, preserve the `name`, `tank_id`, `ip`, `port`, `unit`, register addresses, scale fields, and `enabled` flag pattern used by the default registry.
- When adding a new API endpoint or poller, keep the object shapes and response fields consistent with the dashboard contract already shown in the route module and the README examples.

## Local development workflow

Use the repository-provided commands:

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
copy .env.example .env
mkdir -p data
python -m uvicorn app.main:app --host 0.0.0.0 --port 3000
```

When running Docker, prefer the compose file already in the repository rather than inventing a second deployment path.

## Testing and validation

- The visible regression test in [tests/test_fy600_multidevice.py](tests/test_fy600_multidevice.py) checks that the default FY600 registry exposes the expected two configured devices.
- Use the repository’s existing Python test style; the test suite is small and centered on configuration and device-registry expectations.
- Before claiming a fix, validate with a real command in the workspace, for example `python -m unittest discover -s tests`.

## Useful constraints for AI agents

- Do not copy or duplicate the repository documentation into another file. Link to the existing docs instead.
- Follow the existing project structure; new files should sit where the current modules already define boundaries.
- Prefer minimal diffs and avoid changing the external API contract unless the task explicitly calls for it.
