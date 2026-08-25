import unittest

from process_concurrency.anomaly.process_anomaly import ProcessAnomalyDetector


class TestProcessAnomaly(unittest.TestCase):
    def setUp(self):
        self.detector = ProcessAnomalyDetector()

    def make_observation(self, pid, name="python", cpu_percent=0.0, status="running", cpu_time=0.0):
        return {
            "pid": pid,
            "name": name,
            "cpu_percent": cpu_percent,
            "status": status,
            "timestamp": f"2024-01-01T00:00:{pid:02d}",
            "cpu_times": {"user": cpu_time, "system": 0.0},
        }

    def test_normal_cpu_process_no_runaway_alert(self):
        alerts = []
        for value in [12.0, 15.0, 10.0, 8.0, 9.0]:
            alerts.extend(self.detector.record_observation(self.make_observation(100, cpu_percent=value)))
        self.assertEqual(alerts, [])

    def test_one_high_cpu_observation_no_runaway_alert(self):
        alerts = self.detector.record_observation(self.make_observation(101, cpu_percent=95.0))
        self.assertEqual(alerts, [])

    def test_fewer_than_required_consecutive_observations_no_runaway_alert(self):
        alerts = []
        for _ in range(4):
            alerts.extend(self.detector.record_observation(self.make_observation(102, cpu_percent=95.0)))
        self.assertEqual(alerts, [])

    def test_high_cpu_for_required_number_of_consecutive_observations_runaway_warning(self):
        alerts = []
        for _ in range(5):
            alerts.extend(self.detector.record_observation(self.make_observation(103, cpu_percent=95.0)))
        runaway = [alert for alert in alerts if alert["category"] == "runaway_process"]
        self.assertTrue(runaway)
        self.assertEqual(runaway[0]["severity"], "WARNING")
        self.assertEqual(runaway[0]["pid"], 103)

    def test_cpu_falls_below_threshold_resets_counter(self):
        for _ in range(4):
            self.detector.record_observation(self.make_observation(104, cpu_percent=95.0))
        self.detector.record_observation(self.make_observation(104, cpu_percent=20.0))
        alerts = []
        for _ in range(5):
            alerts.extend(self.detector.record_observation(self.make_observation(104, cpu_percent=95.0)))
        runaway = [alert for alert in alerts if alert["category"] == "runaway_process"]
        self.assertTrue(runaway)

    def test_zombie_process_warning(self):
        alerts = self.detector.record_observation(self.make_observation(105, name="defunct", status="zombie"))
        zombie = [alert for alert in alerts if alert["category"] == "zombie_process"]
        self.assertTrue(zombie)
        self.assertEqual(zombie[0]["severity"], "WARNING")

    def test_missing_or_invalid_process_data_is_safe(self):
        invalid = [
            {"pid": 106, "cpu_percent": 90.0, "status": "running"},
            {"pid": 107, "name": "python", "status": "running"},
            {"pid": 108, "name": None, "cpu_percent": 95.0, "status": "running"},
            {"pid": 109, "name": "python", "cpu_percent": "bad", "status": "running"},
        ]
        for item in invalid:
            result = self.detector.record_observation(item)
            self.assertIsInstance(result, list)
            self.assertNotIsInstance(result, Exception)

    def test_bounded_history_does_not_grow_indefinitely(self):
        detector = ProcessAnomalyDetector(history_limit=3)
        for index in range(10):
            detector.record_observation(self.make_observation(200 + index, cpu_percent=50.0))
        history = detector.history.get(200 + 9)
        self.assertIsNotNone(history)
        self.assertLessEqual(len(history), 3)

    def test_single_low_cpu_observation_does_not_trigger_starvation(self):
        alert = self.detector.record_observation(self.make_observation(300, cpu_percent=1.0, cpu_time=0.1))
        self.assertEqual(alert, [])

    def test_sustained_active_low_cpu_with_cpu_time_delta_triggers_starvation(self):
        alerts = []
        for index in range(15):
            alerts.extend(
                self.detector.record_observation(
                    self.make_observation(
                        301,
                        cpu_percent=1.0,
                        status="running",
                        cpu_time=index * 0.02,
                    )
                )
            )

        starvation = [alert for alert in alerts if alert["category"] == "possible_cpu_starvation"]
        self.assertEqual(len(starvation), 1)

    def test_sleeping_process_with_low_cpu_does_not_trigger_starvation(self):
        alerts = []
        for index in range(15):
            alerts.extend(
                self.detector.record_observation(
                    self.make_observation(
                        302,
                        cpu_percent=0.0,
                        status="sleeping",
                        cpu_time=index * 0.02,
                    )
                )
            )

        self.assertEqual(alerts, [])


if __name__ == "__main__":
    unittest.main()
