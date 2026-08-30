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


# ===================================================================
# Phase 5: I/O Alert Integration Tests
# ===================================================================


class TestAddIOAnomalyAlerts(unittest.TestCase):
    """Tests for AlertEngine.add_io_anomaly_alerts()."""

    def test_spike_low_severity(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "low",
                "reason": "I/O spike detected: 5.1x baseline.",
                "current_rate": 51000.0,
                "baseline_rate": 10000.0,
                "ratio": 5.1,
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=10, process_name="db")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].category, "io_spike")
        self.assertEqual(alerts[0].severity, "INFO")
        self.assertEqual(alerts[0].pid, 10)

    def test_spike_medium_severity(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "medium",
                "reason": "Spike 8x.",
                "current_rate": 80000.0,
                "baseline_rate": 10000.0,
                "ratio": 8.0,
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=10)
        self.assertEqual(alerts[0].severity, "WARNING")

    def test_spike_high_severity(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "high",
                "reason": "Big spike.",
                "current_rate": 100000.0,
                "baseline_rate": 10000.0,
                "ratio": 10.0,
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=10)
        self.assertEqual(alerts[0].severity, "CRITICAL")

    def test_spike_critical_severity(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "critical",
                "reason": "Extreme spike.",
                "current_rate": 500000.0,
                "baseline_rate": 10000.0,
                "ratio": 50.0,
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=10)
        self.assertEqual(alerts[0].severity, "CRITICAL")

    def test_stall_alert_created(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "io_stall": {
                "anomaly": True,
                "type": "io_stall",
                "severity": "high",
                "reason": "I/O stall detected.",
                "last_active_rate": 200000.0,
                "silent_observations": 5,
            },
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=20)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].category, "io_stall")
        self.assertEqual(alerts[0].severity, "CRITICAL")

    def test_sustained_high_io_alert_created(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {
                "anomaly": True,
                "type": "sustained_high_io",
                "severity": "medium",
                "reason": "Sustained high I/O for 7 observations.",
                "consecutive_high_count": 7,
                "average_high_rate": 6000000.0,
            },
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=30)
        self.assertEqual(alerts[0].category, "sustained_high_io")
        self.assertEqual(alerts[0].severity, "WARNING")

    def test_rw_ratio_shift_alert_created(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {
                "anomaly": True,
                "type": "rw_ratio_shift",
                "severity": "low",
                "reason": "R/W ratio shift detected.",
                "current_ratio": 10.0,
                "baseline_ratio": 1.0,
                "ratio_of_ratios": 10.0,
            },
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=40)
        self.assertEqual(alerts[0].category, "rw_ratio_shift")
        self.assertEqual(alerts[0].severity, "INFO")

    def test_multiple_anomalies_all_triggered(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "high",
                "reason": "Spike.",
                "current_rate": 100000.0,
                "baseline_rate": 10000.0,
                "ratio": 10.0,
            },
            "io_stall": {
                "anomaly": True,
                "type": "io_stall",
                "severity": "critical",
                "reason": "Stall.",
                "last_active_rate": 500000.0,
                "silent_observations": 10,
            },
            "sustained_high_io": {
                "anomaly": True,
                "type": "sustained_high_io",
                "severity": "low",
                "reason": "Sustained.",
                "consecutive_high_count": 5,
                "average_high_rate": 6000000.0,
            },
            "rw_ratio_shift": {
                "anomaly": True,
                "type": "rw_ratio_shift",
                "severity": "medium",
                "reason": "Shift.",
                "current_ratio": 20.0,
                "baseline_ratio": 2.0,
                "ratio_of_ratios": 10.0,
            },
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=50, process_name="writer")
        self.assertEqual(len(alerts), 4)
        categories = {a.category for a in alerts}
        self.assertEqual(
            categories,
            {"io_spike", "io_stall", "sustained_high_io", "rw_ratio_shift"},
        )

    def test_no_anomaly_returns_empty(self):
        engine = AlertEngine()
        result = {
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        self.assertEqual(alerts, [])

    def test_non_dict_input_returns_empty(self):
        engine = AlertEngine()
        self.assertEqual(engine.add_io_anomaly_alerts(None), [])
        self.assertEqual(engine.add_io_anomaly_alerts("bad"), [])
        self.assertEqual(engine.add_io_anomaly_alerts(42), [])

    def test_missing_detector_key_treated_as_no_anomaly(self):
        engine = AlertEngine()
        result = {
            "io_spike": {"anomaly": True, "type": "io_spike", "severity": "low", "reason": "Spike."},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].category, "io_spike")

    def test_sub_dict_without_anomaly_key_skipped(self):
        engine = AlertEngine()
        result = {
            "io_spike": {"type": "io_spike", "severity": "low"},
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        self.assertEqual(alerts, [])

    def test_anomaly_false_skipped(self):
        engine = AlertEngine()
        result = {
            "io_spike": {"anomaly": False, "type": "io_spike", "severity": "low", "reason": "Spike."},
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        self.assertEqual(alerts, [])

    def test_non_dict_sub_entry_skipped(self):
        engine = AlertEngine()
        result = {
            "io_spike": "bad",
            "io_stall": None,
            "sustained_high_io": 42,
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        self.assertEqual(alerts, [])

    def test_message_includes_process_name(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "medium",
                "reason": "Spike.",
                "current_rate": 50000.0,
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=10, process_name="nginx")
        self.assertIn("process=nginx", alerts[0].message)

    def test_message_includes_pid(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "low",
                "reason": "Spike.",
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=99)
        self.assertIn("pid=99", alerts[0].message)

    def test_message_no_pid_no_process_name(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "low",
                "reason": "Spike.",
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result)
        self.assertIn("Spike.", alerts[0].message)
        self.assertNotIn("pid=", alerts[0].message)
        self.assertNotIn("process=", alerts[0].message)

    def test_message_includes_reason(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "low",
                "reason": "I/O spike detected: 6x baseline.",
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        self.assertIn("I/O spike detected: 6x baseline.", alerts[0].message)

    def test_evidence_included_in_message(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "low",
                "reason": "Spike.",
                "current_rate": 50000.0,
                "baseline_rate": 10000.0,
                "ratio": 5.0,
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        msg = alerts[0].message
        self.assertIn("Evidence:", msg)
        self.assertIn("current_rate=50000.0", msg)
        self.assertIn("baseline_rate=10000.0", msg)
        self.assertIn("ratio=5.0", msg)

    def test_suggested_action_from_actions_dict(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_stall": {
                "anomaly": True,
                "type": "io_stall",
                "severity": "high",
                "reason": "Stall.",
                "last_active_rate": 100000.0,
                "silent_observations": 5,
            },
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        self.assertEqual(
            alerts[0].suggested_action,
            "Check if the process is hung or blocked on I/O.",
        )

    def test_deduplication_suppresses_duplicate_io_alerts(self):
        engine = AlertEngine(duplicate_window=60)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "low",
                "reason": "Spike.",
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        first = engine.add_io_anomaly_alerts(result, pid=1)
        second = engine.add_io_anomaly_alerts(result, pid=1)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(engine.alerts), 1)

    def test_different_pids_not_deduplicated(self):
        engine = AlertEngine(duplicate_window=60)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "low",
                "reason": "Spike.",
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        engine.add_io_anomaly_alerts(result, pid=1)
        engine.add_io_anomaly_alerts(result, pid=2)
        self.assertEqual(len(engine.alerts), 2)

    def test_default_severity_for_unknown_raw(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "bogus",
                "reason": "Spike.",
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        self.assertEqual(alerts[0].severity, "WARNING")

    def test_io_stall_evidence_fields(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "io_stall": {
                "anomaly": True,
                "type": "io_stall",
                "severity": "medium",
                "reason": "Stall.",
                "last_active_rate": 200000.0,
                "silent_observations": 4,
            },
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        msg = alerts[0].message
        self.assertIn("last_active_rate=200000.0", msg)
        self.assertIn("silent_observations=4", msg)

    def test_sustained_high_io_evidence_fields(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {
                "anomaly": True,
                "type": "sustained_high_io",
                "severity": "low",
                "reason": "Sustained.",
                "consecutive_high_count": 8,
                "average_high_rate": 7000000.0,
            },
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        msg = alerts[0].message
        self.assertIn("consecutive_high_count=8", msg)
        self.assertIn("average_high_rate=7000000.0", msg)

    def test_rw_ratio_shift_evidence_fields(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {
                "anomaly": True,
                "type": "rw_ratio_shift",
                "severity": "medium",
                "reason": "Shift.",
                "current_ratio": 15.0,
                "baseline_ratio": 1.5,
                "ratio_of_ratios": 10.0,
            },
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        msg = alerts[0].message
        self.assertIn("current_ratio=15.0", msg)
        self.assertIn("baseline_ratio=1.5", msg)
        self.assertIn("ratio_of_ratios=10.0", msg)

    def test_io_spike_default_reason_fallback(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "low",
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=1)
        self.assertIn("I/O spike detected.", alerts[0].message)


class TestAddIOClassificationChangeAlert(unittest.TestCase):
    """Tests for AlertEngine.add_io_classification_change_alert()."""

    def test_change_creates_alert(self):
        engine = AlertEngine(duplicate_window=0)
        alert = engine.add_io_classification_change_alert(
            pid=10, process_name="db",
            old_classification="IO_BOUND", new_classification="CPU_BOUND",
        )
        self.assertIsNotNone(alert)
        self.assertEqual(alert.category, "io_classification_change")
        self.assertEqual(alert.severity, "WARNING")
        self.assertEqual(alert.pid, 10)

    def test_same_classification_returns_none(self):
        engine = AlertEngine(duplicate_window=0)
        alert = engine.add_io_classification_change_alert(
            pid=10, process_name="db",
            old_classification="IO_BOUND", new_classification="IO_BOUND",
        )
        self.assertIsNone(alert)

    def test_message_includes_both_classifications(self):
        engine = AlertEngine(duplicate_window=0)
        alert = engine.add_io_classification_change_alert(
            pid=10, process_name="db",
            old_classification="IO_BOUND", new_classification="CPU_BOUND",
        )
        self.assertIn("IO_BOUND", alert.message)
        self.assertIn("CPU_BOUND", alert.message)
        self.assertIn("->", alert.message)

    def test_message_includes_process_name(self):
        engine = AlertEngine(duplicate_window=0)
        alert = engine.add_io_classification_change_alert(
            pid=10, process_name="nginx",
            old_classification="BALANCED", new_classification="IO_BOUND",
        )
        self.assertIn("process=nginx", alert.message)

    def test_message_includes_pid(self):
        engine = AlertEngine(duplicate_window=0)
        alert = engine.add_io_classification_change_alert(
            pid=42, process_name="db",
            old_classification="IDLE", new_classification="BALANCED",
        )
        self.assertIn("pid=42", alert.message)

    def test_no_process_name_no_pid(self):
        engine = AlertEngine(duplicate_window=0)
        alert = engine.add_io_classification_change_alert(
            pid=None, process_name=None,
            old_classification="IDLE", new_classification="BALANCED",
        )
        self.assertNotIn("process=", alert.message)
        self.assertNotIn("pid=", alert.message)
        self.assertIn("IDLE -> BALANCED", alert.message)

    def test_reason_included_in_message(self):
        engine = AlertEngine(duplicate_window=0)
        alert = engine.add_io_classification_change_alert(
            pid=10, process_name="db",
            old_classification="IO_BOUND", new_classification="CPU_BOUND",
            reason="CPU usage increased to 95%.",
        )
        self.assertIn("CPU usage increased to 95%.", alert.message)

    def test_no_reason_message_still_works(self):
        engine = AlertEngine(duplicate_window=0)
        alert = engine.add_io_classification_change_alert(
            pid=10, process_name="db",
            old_classification="IO_BOUND", new_classification="CPU_BOUND",
        )
        self.assertIn("IO_BOUND -> CPU_BOUND", alert.message)

    def test_suggested_action_is_correct(self):
        engine = AlertEngine(duplicate_window=0)
        alert = engine.add_io_classification_change_alert(
            pid=10, process_name="db",
            old_classification="IO_BOUND", new_classification="CPU_BOUND",
        )
        self.assertEqual(
            alert.suggested_action,
            "Review the I/O behavior change for the process.",
        )

    def test_severity_always_warning(self):
        engine = AlertEngine(duplicate_window=0)
        for old, new in [
            ("IDLE", "CPU_BOUND"),
            ("IO_BOUND", "BALANCED"),
            ("CPU_BOUND", "IDLE"),
            ("BALANCED", "IO_BOUND"),
        ]:
            alert = engine.add_io_classification_change_alert(
                pid=10, process_name="db",
                old_classification=old, new_classification=new,
            )
            self.assertEqual(alert.severity, "WARNING")

    def test_deduplication_suppresses(self):
        engine = AlertEngine(duplicate_window=60)
        a1 = engine.add_io_classification_change_alert(
            pid=10, process_name="db",
            old_classification="IO_BOUND", new_classification="CPU_BOUND",
        )
        a2 = engine.add_io_classification_change_alert(
            pid=10, process_name="db",
            old_classification="IO_BOUND", new_classification="CPU_BOUND",
        )
        self.assertIsNotNone(a1)
        self.assertIsNone(a2)
        self.assertEqual(len(engine.alerts), 1)

    def test_different_pids_not_deduplicated(self):
        engine = AlertEngine(duplicate_window=60)
        engine.add_io_classification_change_alert(
            pid=10, process_name="db",
            old_classification="IO_BOUND", new_classification="CPU_BOUND",
        )
        engine.add_io_classification_change_alert(
            pid=20, process_name="db",
            old_classification="IO_BOUND", new_classification="CPU_BOUND",
        )
        self.assertEqual(len(engine.alerts), 2)

    def test_returns_alert_object(self):
        engine = AlertEngine(duplicate_window=0)
        alert = engine.add_io_classification_change_alert(
            pid=5, process_name="writer",
            old_classification="BALANCED", new_classification="IO_BOUND",
        )
        self.assertIsInstance(alert, Alert)
        self.assertEqual(alert.pid, 5)

    def test_all_four_transitions(self):
        engine = AlertEngine(duplicate_window=0)
        transitions = [
            ("IDLE", "CPU_BOUND"),
            ("IDLE", "IO_BOUND"),
            ("IO_BOUND", "CPU_BOUND"),
            ("CPU_BOUND", "BALANCED"),
        ]
        for old, new in transitions:
            alert = engine.add_io_classification_change_alert(
                pid=1, process_name="test",
                old_classification=old, new_classification=new,
            )
            self.assertIsNotNone(alert)
            self.assertIn(old, alert.message)
            self.assertIn(new, alert.message)
        self.assertEqual(len(engine.alerts), 4)


class TestBuildIOEvidence(unittest.TestCase):
    """Tests for AlertEngine._build_io_evidence()."""

    def test_empty_dict(self):
        self.assertEqual(AlertEngine._build_io_evidence({}), "")

    def test_only_type_field(self):
        result = AlertEngine._build_io_evidence({"type": "io_spike"})
        self.assertEqual(result, "type=io_spike")

    def test_type_none_excluded(self):
        result = AlertEngine._build_io_evidence({"type": "none"})
        self.assertEqual(result, "")

    def test_current_rate_and_baseline(self):
        result = AlertEngine._build_io_evidence({
            "current_rate": 50000.0,
            "baseline_rate": 10000.0,
        })
        self.assertIn("current_rate=50000.0", result)
        self.assertIn("baseline_rate=10000.0", result)

    def test_ratio_fields(self):
        result = AlertEngine._build_io_evidence({
            "ratio": 5.0,
            "ratio_of_ratios": 10.0,
        })
        self.assertIn("ratio=5.0", result)
        self.assertIn("ratio_of_ratios=10.0", result)

    def test_stall_fields(self):
        result = AlertEngine._build_io_evidence({
            "last_active_rate": 200000.0,
            "silent_observations": 4,
        })
        self.assertIn("last_active_rate=200000.0", result)
        self.assertIn("silent_observations=4", result)

    def test_sustained_fields(self):
        result = AlertEngine._build_io_evidence({
            "consecutive_high_count": 8,
            "average_high_rate": 7000000.0,
        })
        self.assertIn("consecutive_high_count=8", result)
        self.assertIn("average_high_rate=7000000.0", result)

    def test_rw_ratio_fields(self):
        result = AlertEngine._build_io_evidence({
            "current_ratio": 15.0,
            "baseline_ratio": 1.5,
        })
        self.assertIn("current_ratio=15.0", result)
        self.assertIn("baseline_ratio=1.5", result)

    def test_none_values_excluded(self):
        result = AlertEngine._build_io_evidence({
            "current_rate": None,
            "baseline_rate": None,
            "ratio": None,
        })
        self.assertEqual(result, "")

    def test_mixed_fields(self):
        result = AlertEngine._build_io_evidence({
            "type": "io_spike",
            "current_rate": 50000.0,
            "baseline_rate": None,
            "ratio": 5.0,
            "silent_observations": None,
        })
        self.assertIn("type=io_spike", result)
        self.assertIn("current_rate=50000.0", result)
        self.assertNotIn("baseline_rate", result)
        self.assertIn("ratio=5.0", result)
        self.assertNotIn("silent_observations", result)

    def test_all_known_fields(self):
        result = AlertEngine._build_io_evidence({
            "type": "io_spike",
            "current_rate": 50000.0,
            "baseline_rate": 10000.0,
            "ratio": 5.0,
            "last_active_rate": 200000.0,
            "silent_observations": 4,
            "consecutive_high_count": 8,
            "average_high_rate": 7000000.0,
            "current_ratio": 15.0,
            "baseline_ratio": 1.5,
            "ratio_of_ratios": 10.0,
        })
        for field in [
            "type=io_spike",
            "current_rate=50000.0",
            "baseline_rate=10000.0",
            "ratio=5.0",
            "last_active_rate=200000.0",
            "silent_observations=4",
            "consecutive_high_count=8",
            "average_high_rate=7000000.0",
            "current_ratio=15.0",
            "baseline_ratio=1.5",
            "ratio_of_ratios=10.0",
        ]:
            self.assertIn(field, result)

    def test_unknown_fields_ignored(self):
        result = AlertEngine._build_io_evidence({
            "unknown_field": "foo",
            "another": 42,
        })
        self.assertEqual(result, "")


class TestIOAnomalyToAlertIntegration(unittest.TestCase):
    """Integration tests: io_anomaly results → alert engine → Alert objects."""

    def test_full_pipeline_spike(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "high",
                "reason": "I/O spike detected: current rate (100000 B/s) is 10.0x the baseline.",
                "current_rate": 100000.0,
                "baseline_rate": 10000.0,
                "ratio": 10.0,
                "num_observations": 10,
                "thresholds": {"spike_multiplier": 5.0, "min_rate": 10000.0},
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none",
                         "reason": "No stall.", "last_active_rate": 0.0,
                         "silent_observations": 0, "num_observations": 10,
                         "thresholds": {}},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none",
                                  "reason": "No sustained.", "consecutive_high_count": 0,
                                  "average_high_rate": 0.0, "num_observations": 10,
                                  "thresholds": {}},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none",
                               "reason": "No shift.", "current_ratio": 1.0,
                               "baseline_ratio": 1.0, "ratio_of_ratios": 1.0,
                               "num_observations": 10, "thresholds": {}},
            "any_anomaly": True,
            "most_severe": "high",
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=100, process_name="db")
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.category, "io_spike")
        self.assertEqual(alert.severity, "CRITICAL")
        self.assertEqual(alert.pid, 100)
        self.assertIn("db", alert.message)
        self.assertIn("10.0x", alert.message)
        self.assertIn("Evidence:", alert.message)

    def test_full_pipeline_stall(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "io_stall": {
                "anomaly": True,
                "type": "io_stall",
                "severity": "critical",
                "reason": "I/O stall detected: process was active (500000 B/s) but silent.",
                "last_active_rate": 500000.0,
                "silent_observations": 10,
                "num_observations": 20,
                "thresholds": {},
            },
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
            "any_anomaly": True,
            "most_severe": "critical",
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=200, process_name="writer")
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.category, "io_stall")
        self.assertEqual(alert.severity, "CRITICAL")
        self.assertIn("writer", alert.message)
        self.assertIn("500000.0", alert.message)

    def test_full_pipeline_sustained(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {
                "anomaly": True,
                "type": "sustained_high_io",
                "severity": "medium",
                "reason": "Sustained high I/O for 7 observations.",
                "consecutive_high_count": 7,
                "average_high_rate": 6000000.0,
                "num_observations": 15,
                "thresholds": {},
            },
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
            "any_anomaly": True,
            "most_severe": "medium",
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=300, process_name="backup")
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.category, "sustained_high_io")
        self.assertEqual(alert.severity, "WARNING")
        self.assertIn("backup", alert.message)

    def test_full_pipeline_rw_ratio_shift(self):
        engine = AlertEngine(duplicate_window=0)
        result = {
            "io_spike": {"anomaly": False, "type": "none", "severity": "none"},
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {
                "anomaly": True,
                "type": "rw_ratio_shift",
                "severity": "high",
                "reason": "R/W ratio shift detected: 10x change.",
                "current_ratio": 10.0,
                "baseline_ratio": 1.0,
                "ratio_of_ratios": 10.0,
                "num_observations": 10,
                "thresholds": {},
            },
            "any_anomaly": True,
            "most_severe": "high",
        }
        alerts = engine.add_io_anomaly_alerts(result, pid=400, process_name="postgres")
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.category, "rw_ratio_shift")
        self.assertEqual(alert.severity, "CRITICAL")
        self.assertIn("postgres", alert.message)

    def test_classification_change_then_anomaly_combined(self):
        engine = AlertEngine(duplicate_window=0)
        engine.add_io_classification_change_alert(
            pid=50, process_name="db",
            old_classification="IO_BOUND", new_classification="CPU_BOUND",
            reason="CPU usage spiked.",
        )
        anomaly_result = {
            "io_spike": {
                "anomaly": True,
                "type": "io_spike",
                "severity": "medium",
                "reason": "I/O spike.",
                "current_rate": 80000.0,
                "baseline_rate": 10000.0,
                "ratio": 8.0,
            },
            "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
            "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
            "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
        }
        engine.add_io_anomaly_alerts(anomaly_result, pid=50, process_name="db")
        alerts = engine.alerts
        self.assertEqual(len(alerts), 2)
        categories = {a.category for a in alerts}
        self.assertEqual(categories, {"io_classification_change", "io_spike"})
        for a in alerts:
            self.assertEqual(a.pid, 50)

    def test_multiple_processes_independent(self):
        engine = AlertEngine(duplicate_window=0)
        for pid, name in [(1, "a"), (2, "b"), (3, "c")]:
            result = {
                "io_spike": {
                    "anomaly": True,
                    "type": "io_spike",
                    "severity": "low",
                    "reason": f"Spike for {name}.",
                },
                "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
                "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
                "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
            }
            engine.add_io_anomaly_alerts(result, pid=pid, process_name=name)
        self.assertEqual(len(engine.alerts), 3)
        pids = [a.pid for a in engine.alerts]
        self.assertEqual(sorted(pids), [1, 2, 3])

    def test_alert_history_bounded_with_io(self):
        engine = AlertEngine(history_limit=3, duplicate_window=0)
        for pid in range(5):
            result = {
                "io_spike": {
                    "anomaly": True,
                    "type": "io_spike",
                    "severity": "low",
                    "reason": "Spike.",
                },
                "io_stall": {"anomaly": False, "type": "none", "severity": "none"},
                "sustained_high_io": {"anomaly": False, "type": "none", "severity": "none"},
                "rw_ratio_shift": {"anomaly": False, "type": "none", "severity": "none"},
            }
            engine.add_io_anomaly_alerts(result, pid=pid)
        self.assertEqual(len(engine.alerts), 3)
        self.assertEqual([a.pid for a in engine.alerts], [2, 3, 4])


if __name__ == "__main__":
    unittest.main()
