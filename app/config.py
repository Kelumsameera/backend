from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_FY600_DEVICES: list[dict[str, Any]] = [
    {
        "name": "pump_house_tank",
        "tank_id": "pump_house_tank",
        "ip": "192.168.0.16",
        "port": 502,
        "unit": 1,
        "level_register": 0x008A,  # REQUIRES CONFIRMATION
        "setpoint_register": 0x0000,  # REQUIRES CONFIRMATION
        "output_register": 0x0087,  # REQUIRES CONFIRMATION
        "level_scale": 1.0,
        "setpoint_scale": 10.0,
        "output_scale": 10.0,
        "timeout": 2.0,
        "retries": 2,
        "retry_delay": 0.2,
        "reconnect_delay": 3.0,
        "stale_after_seconds": 30,
        "enabled": True,
    },
    {
        "name": "main_tank",
        "tank_id": "main_tank",
        "ip": "192.168.0.18",
        "port": 502,
        "unit": 1,
        "level_register": 0x008A,  # REQUIRES CONFIRMATION
        "setpoint_register": 0x0000,  # REQUIRES CONFIRMATION
        "output_register": 0x0087,  # REQUIRES CONFIRMATION
        "level_scale": 1.0,
        "setpoint_scale": 10.0,
        "output_scale": 10.0,
        "timeout": 2.0,
        "retries": 2,
        "retry_delay": 0.2,
        "reconnect_delay": 3.0,
        "stale_after_seconds": 30,
        "enabled": True,
    },
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 5000

    # Pressure
    pressure_production_ip: str = "192.168.0.8"
    pressure_production_unit: int = 1
    pressure_assembly_ip: str = "192.168.0.17"
    pressure_assembly_unit: int = 2
    pressure_port: int = 502
    pressure_register: int = 0
    pressure_poll_interval: float = 2.0

    # FY600 water tank - legacy single-device defaults kept for compatibility
    fy600_ip: str = "192.168.0.16"
    fy600_unit: int = 1
    fy600_port: int = 502
    fy600_poll_interval: float = 2.0

    # New scalable FY600 registry. This remains configurable in code and via
    # environment overrides when a list is provided as a JSON string. If this
    # isn’t provided, the default registry above becomes the source of truth.
    fy600_devices: list[dict[str, Any]] = DEFAULT_FY600_DEVICES

    # Storage protection
    retention_days: int = 14
    history_max_rows: int = 5000
    cleanup_interval_hours: float = 6.0
    database_path: str = "./data/modbus.db"


settings = Settings()
