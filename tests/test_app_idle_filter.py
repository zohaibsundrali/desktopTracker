import unittest

from app_monitor import AppMonitor


class AppIdleFilterTests(unittest.TestCase):
    def test_standalone_monitor_keeps_foreground_compatibility(self):
        monitor = AppMonitor.__new__(AppMonitor)
        monitor._activity_probe = None
        self.assertTrue(monitor._input_is_active())

    def test_coordinator_probe_controls_payable_app_time(self):
        monitor = AppMonitor.__new__(AppMonitor)
        monitor._activity_probe = lambda: False
        self.assertFalse(monitor._input_is_active())
        monitor._activity_probe = lambda: True
        self.assertTrue(monitor._input_is_active())

    def test_probe_failure_fails_closed(self):
        monitor = AppMonitor.__new__(AppMonitor)
        monitor._activity_probe = lambda: (_ for _ in ()).throw(RuntimeError('broken'))
        self.assertFalse(monitor._input_is_active())


if __name__ == '__main__':
    unittest.main()
