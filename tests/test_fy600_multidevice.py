import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings


class TestFY600MultiDeviceConfiguration(unittest.TestCase):
    def test_settings_exposes_a_registry_with_two_devices(self):
        devices = Settings().fy600_devices
        self.assertIsInstance(devices, list)
        self.assertEqual(2, len(devices))

        names = {device.get("name") for device in devices}
        self.assertIn("pump_house_tank", names)
        self.assertIn("main_tank", names)

        ips = {device.get("ip") for device in devices}
        self.assertIn("192.168.0.16", ips)
        self.assertIn("192.168.0.18", ips)

    def test_level_scales_match_raw_values(self):
        devices = {d["name"]: d for d in Settings().fy600_devices}
        self.assertEqual(10.0, devices["pump_house_tank"]["level_scale"])
        self.assertEqual(100.0, devices["main_tank"]["level_scale"])
        self.assertEqual(222.30, round(2223.0 / devices["pump_house_tank"]["level_scale"], 2))
        self.assertEqual(630.83, round(63083.0 / devices["main_tank"]["level_scale"], 2))

    def test_settings_rejects_fy600_registry_entries_missing_required_keys(self):
        malformed_devices = [
            {
                "name": "broken_tank",
                "tank_id": "broken_tank",
                "ip": "192.168.0.50",
                "port": 502,
                "unit": 1,
                "level_register": 0x008A,
                # setpoint_register, output_register, and scale fields intentionally omitted
                "enabled": True,
            }
        ]

        with self.assertRaises(ValidationError):
            Settings(fy600_devices=malformed_devices)


if __name__ == "__main__":
    unittest.main()
