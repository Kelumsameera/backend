import unittest

from app.config import settings


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


if __name__ == "__main__":
    unittest.main()
