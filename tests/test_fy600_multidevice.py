import unittest

from pydantic import ValidationError

from app.config import Settings, settings


class TestFY600MultiDeviceConfiguration(unittest.TestCase):
    def test_settings_exposes_a_registry_with_two_devices(self):
        devices = settings.fy600_devices
        self.assertIsInstance(devices, list)
        self.assertEqual(2, len(devices))

        names = {device.get("name") for device in devices}
        self.assertIn("pump_house_tank", names)
        self.assertIn("main_tank", names)

        ips = {device.get("ip") for device in devices}
        self.assertIn("192.168.0.16", ips)
        self.assertIn("192.168.0.18", ips)

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
