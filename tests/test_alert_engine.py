import unittest

from dashboard.alert_engine import Alert, AlertEngine


class TestAlertEngine(unittest.TestCase):
    def test_creates_warning_alert(self):
        engine = AlertEngine()
        alert = engine.add({"category": "runaway_process", "pid": 123, "name": "python"})

        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "WARNING")
        self.assertEqual(alert.suggested_action, "Investigate the process.")
        self.assertEqual(alert.pid, 123)

    def test_creates_critical_alert(self):
        engine = AlertEngine()
        alert = engine.add({"category": "deadlock"})

        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "CRITICAL")
        self.assertEqual(alert.message, "Potential deadlock detected.")

    def test_converts_anomaly_alert(self):
        engine = AlertEngine()
        alert = engine.add(
            {
                "timestamp": "2024-01-01T00:00:00+00:00",
                "category": "possible_cpu_starvation",
                "severity": "WARNING",
                "pid": 42,
                "name": "worker",
                "observed_value": 1.2,
            }
        )

        self.assertEqual(alert.category, "cpu_starvation")
        self.assertIn("CPU=1.2", alert.message)
        self.assertEqual(alert.suggested_action, "Investigate CPU scheduling and process activity.")

    def test_converts_deadlock_results(self):
        engine = AlertEngine()
        cycle_alerts = engine.add_deadlock_cycle({"has_cycle": True})
        unsafe_alerts = engine.add_unsafe_state({"safe": False})

        self.assertEqual(cycle_alerts[0].category, "deadlock")
        self.assertEqual(unsafe_alerts[0].category, "unsafe_state")
        self.assertEqual(unsafe_alerts[0].severity, "CRITICAL")

    def test_duplicate_alerts_are_suppressed(self):
        engine = AlertEngine(duplicate_window=60)
        payload = {"category": "zombie_process", "pid": 7, "name": "defunct"}

        self.assertIsNotNone(engine.add(payload))
        self.assertIsNone(engine.add(payload))
        self.assertEqual(len(engine.alerts), 1)

    def test_history_is_bounded(self):
        engine = AlertEngine(history_limit=2, duplicate_window=0)
        for pid in (1, 2, 3):
            engine.add({"category": "zombie_process", "pid": pid})

        self.assertEqual(len(engine.alerts), 2)
        self.assertEqual([alert.pid for alert in engine.alerts], [2, 3])

    def test_alert_dataclass_is_supported(self):
        engine = AlertEngine()
        alert = engine.add(Alert("now", "INFO", "test", "Message", "Inspect"))

        self.assertEqual(alert.category, "test")
        self.assertIsNone(alert.pid)


if __name__ == "__main__":
    unittest.main()
