"""
tests/test_iopulse_panel.py – Non-GUI Tests for the IOPulse Dashboard Tab
OS Sentinel → IOPulse (Phase 6)

These tests verify the pure data-preparation and formatting helpers used
by dashboard/iopulse_panel.py.  They do NOT instantiate Tkinter or rely
on an actual running machine / process — all inputs are constructed
dicts matching the shapes returned by the IOPulse intelligence modules.
"""

import unittest

from dashboard.iopulse_panel import (
    extract_anomaly_evidence,
    format_bytes_per_sec,
    format_classification,
    format_severity,
    prepare_anomaly_display_data,
    prepare_classification_scatter_data,
    prepare_explanation,
    prepare_overview_data,
    prepare_process_table_data,
    prepare_scheduling_display_data,
    prepare_throughput_history,
    validate_refresh_interval,
)


def make_metrics(
    pid, name="proc", cpu=10.0, read=1000.0, write=500.0, total=None
):
    """Build a metric dict shaped like ProcessIOCollector output."""
    total = total if total is not None else read + write
    return {
        "pid": pid,
        "name": name,
        "state": "running",
        "cpu_percent": cpu,
        "memory_percent": 1.0,
        "read_bytes_per_sec": read,
        "write_bytes_per_sec": write,
        "total_io_bytes_per_sec": total,
        "read_write_ratio": (read / write) if write else 0.0,
        "timestamp": 1000.0 + pid,
    }


def make_classification(pid, name="proc", cls="IDLE", cpu=0.0, io=0.0,
                        confidence=0.0, reason=""):
    """Build a classification dict shaped like ProcessIOClassifier output."""
    return {
        "pid": pid,
        "process_name": name,
        "classification": cls,
        "confidence": confidence,
        "cpu_score": 0.5,
        "io_score": 0.5,
        "cpu_percent": cpu,
        "total_io_bytes_per_sec": io,
        "reason": reason,
    }


def make_health(any_anomaly=False, spike=False, stall=False, sustained=False,
                shift=False, spike_severity="low", spike_reason="Spike.",
                spike_ratio=6.0, spike_current=60000.0, spike_baseline=10000.0):
    """Build an analyze_io_health() result dict."""
    def sub(active, type_, severity, reason, extra):
        base = {
            "anomaly": active,
            "type": type_ if active else "none",
            "severity": severity if active else "none",
            "reason": reason if active else f"No {type_}.",
        }
        base.update(extra)
        return base

    return {
        "io_spike": sub(spike or any_anomaly, "io_spike", spike_severity,
                        spike_reason, {
                            "current_rate": spike_current,
                            "baseline_rate": spike_baseline,
                            "ratio": spike_ratio,
                        }),
        "io_stall": sub(stall, "io_stall", "medium", "Stall.",
                        {"last_active_rate": 200000.0, "silent_observations": 4}),
        "sustained_high_io": sub(sustained, "sustained_high_io", "low",
                                 "Sustained.",
                                 {"consecutive_high_count": 6,
                                  "average_high_rate": 6000000.0}),
        "rw_ratio_shift": sub(shift, "rw_ratio_shift", "high", "Shift.",
                              {"current_ratio": 10.0, "baseline_ratio": 1.0,
                               "ratio_of_ratios": 10.0}),
        "any_anomaly": any_anomaly or spike or stall or sustained or shift,
        "most_severe": "none",
    }


# ===================================================================
# Formatters
# ===================================================================

class TestFormatBytesPerSec(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(format_bytes_per_sec(0), "0 B/s")

    def test_bytes(self):
        self.assertEqual(format_bytes_per_sec(500), "500 B/s")

    def test_kilobytes(self):
        self.assertEqual(format_bytes_per_sec(1500), "1.50 KB/s")

    def test_megabytes(self):
        self.assertEqual(format_bytes_per_sec(2_500_000), "2.50 MB/s")

    def test_gigabytes(self):
        self.assertEqual(format_bytes_per_sec(3_500_000_000), "3.50 GB/s")

    def test_none(self):
        self.assertEqual(format_bytes_per_sec(None), "0 B/s")

    def test_non_numeric(self):
        self.assertEqual(format_bytes_per_sec("abc"), "0 B/s")

    def test_negative_value(self):
        self.assertTrue(format_bytes_per_sec(-5).endswith("B/s"))


class TestFormatClassification(unittest.TestCase):
    def test_cpu_bound(self):
        self.assertEqual(format_classification("CPU_BOUND"), "CPU Bound")

    def test_io_bound(self):
        self.assertEqual(format_classification("IO_BOUND"), "I/O Bound")

    def test_balanced(self):
        self.assertEqual(format_classification("BALANCED"), "Balanced")

    def test_idle(self):
        self.assertEqual(format_classification("IDLE"), "Idle")

    def test_empty_string(self):
        self.assertEqual(format_classification(""), "—")

    def test_none(self):
        self.assertEqual(format_classification(None), "—")

    def test_unknown_falls_back_to_title(self):
        self.assertEqual(format_classification("MY_CLASS"), "My Class")


class TestFormatSeverity(unittest.TestCase):
    def test_none_severity(self):
        self.assertEqual(format_severity("none"), "Normal")

    def test_low(self):
        self.assertEqual(format_severity("low"), "Low")

    def test_medium(self):
        self.assertEqual(format_severity("medium"), "Medium")

    def test_high(self):
        self.assertEqual(format_severity("high"), "High")

    def test_critical(self):
        self.assertEqual(format_severity("critical"), "Critical")

    def test_alert_severities(self):
        self.assertEqual(format_severity("INFO"), "Info")
        self.assertEqual(format_severity("WARNING"), "Warning")
        self.assertEqual(format_severity("CRITICAL"), "Critical")

    def test_unknown_passthrough(self):
        self.assertEqual(format_severity("bogus"), "bogus")


# ===================================================================
# Refresh interval validation
# ===================================================================

class TestValidateRefreshInterval(unittest.TestCase):
    def test_valid_default(self):
        ok, msg = validate_refresh_interval("2000")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_valid_min_boundary(self):
        self.assertTrue(validate_refresh_interval("500")[0])

    def test_valid_max_boundary(self):
        self.assertTrue(validate_refresh_interval("30000")[0])

    def test_whitespace_stripped(self):
        self.assertTrue(validate_refresh_interval("  1000  ")[0])

    def test_integer_only(self):
        ok, msg = validate_refresh_interval("1000")
        self.assertTrue(ok)

    def test_empty_rejected(self):
        ok, msg = validate_refresh_interval("")
        self.assertFalse(ok)
        self.assertIn("empty", msg.lower())

    def test_whitespace_only_rejected(self):
        ok, msg = validate_refresh_interval("   ")
        self.assertFalse(ok)

    def test_none_rejected(self):
        self.assertFalse(validate_refresh_interval(None)[0])

    def test_non_numeric_rejected(self):
        ok, msg = validate_refresh_interval("fast")
        self.assertFalse(ok)
        self.assertIn("whole number", msg.lower())

    def test_float_rejected(self):
        self.assertFalse(validate_refresh_interval("1000.5")[0])

    def test_too_small_rejected(self):
        ok, msg = validate_refresh_interval("499")
        self.assertFalse(ok)
        self.assertIn("at least 500", msg)

    def test_too_large_rejected(self):
        ok, msg = validate_refresh_interval("30001")
        self.assertFalse(ok)
        self.assertIn("at most 30000", msg)


# ===================================================================
# Section A – Overview aggregation
# ===================================================================

class TestPrepareOverviewData(unittest.TestCase):
    def test_empty_everything(self):
        data = prepare_overview_data([], [], [])
        self.assertEqual(data["total_processes"], 0)
        self.assertEqual(data["total_read_throughput"], 0.0)
        self.assertEqual(data["total_write_throughput"], 0.0)
        self.assertEqual(data["total_io_throughput"], 0.0)
        self.assertEqual(data["cpu_bound_count"], 0)
        self.assertEqual(data["io_bound_count"], 0)
        self.assertEqual(data["balanced_count"], 0)
        self.assertEqual(data["idle_count"], 0)
        self.assertEqual(data["active_anomalies"], 0)

    def test_aggregates_throughput(self):
        metrics = [
            make_metrics(1, read=1000.0, write=500.0),
            make_metrics(2, read=2000.0, write=1000.0),
        ]
        data = prepare_overview_data(metrics, [], [])
        self.assertEqual(data["total_processes"], 2)
        self.assertEqual(data["total_read_throughput"], 3000.0)
        self.assertEqual(data["total_write_throughput"], 1500.0)
        self.assertEqual(data["total_io_throughput"], 4500.0)

    def test_counts_classifications(self):
        classifications = [
            make_classification(1, cls="CPU_BOUND"),
            make_classification(2, cls="IO_BOUND"),
            make_classification(3, cls="IO_BOUND"),
            make_classification(4, cls="BALANCED"),
            make_classification(5, cls="IDLE"),
        ]
        data = prepare_overview_data([], classifications, [])
        self.assertEqual(data["cpu_bound_count"], 1)
        self.assertEqual(data["io_bound_count"], 2)
        self.assertEqual(data["balanced_count"], 1)
        self.assertEqual(data["idle_count"], 1)

    def test_unknown_classification_counts_as_idle(self):
        classifications = [make_classification(1, cls="WEIRD")]
        data = prepare_overview_data([], classifications, [])
        self.assertEqual(data["idle_count"], 1)

    def test_counts_active_anomalies(self):
        health = [make_health(any_anomaly=True), make_health(any_anomaly=False),
                  make_health(any_anomaly=False)]
        data = prepare_overview_data([], [], health)
        self.assertEqual(data["active_anomalies"], 1)

    def test_malformed_metrics_ignored(self):
        data = prepare_overview_data(
            [{"pid": 1, "read_bytes_per_sec": "bad"},
             {"pid": 2, "write_bytes_per_sec": None}],
            [], [],
        )
        self.assertEqual(data["total_processes"], 2)
        self.assertEqual(data["total_read_throughput"], 0.0)

    def test_malformed_health_ignored(self):
        data = prepare_overview_data([], [], [None, "garbage", 42])
        self.assertEqual(data["active_anomalies"], 0)


# ===================================================================
# Section B – Process table preparation
# ===================================================================

class TestPrepareProcessTableData(unittest.TestCase):
    def test_empty_inputs(self):
        self.assertEqual(prepare_process_table_data([], [], {}), [])

    def test_metric_without_pid_skipped(self):
        rows = prepare_process_table_data([{"name": "x"}], [], {})
        self.assertEqual(rows, [])

    def test_basic_row_fields(self):
        metrics = [make_metrics(7, name="db", cpu=12.5, read=1000.0, write=500.0)]
        classifications = [make_classification(7, name="db", cls="IO_BOUND",
                                               confidence=0.85, io=1500.0)]
        rows = prepare_process_table_data(metrics, classifications, {})
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["pid"], "7")
        self.assertEqual(row["pid_raw"], 7)
        self.assertEqual(row["name"], "db")
        self.assertEqual(row["cpu"], "12.5")
        self.assertEqual(row["cpu_raw"], 12.5)
        self.assertEqual(row["read_rate"], "1.00 KB/s")
        self.assertEqual(row["write_rate"], "500 B/s")
        self.assertEqual(row["total_io_rate"], "1.50 KB/s")
        self.assertEqual(row["classification"], "I/O Bound")
        self.assertEqual(row["classification_raw"], "IO_BOUND")
        self.assertEqual(row["confidence"], "0.85")
        self.assertEqual(row["status"], "Normal")

    def test_anomaly_status_flag(self):
        metrics = [make_metrics(7, name="db")]
        health = {7: make_health(any_anomaly=True, spike=True, spike_severity="high")}
        rows = prepare_process_table_data(metrics, [], health)
        self.assertIn("io_spike", rows[0]["status"])
        self.assertNotEqual(rows[0]["status"], "Normal")

    def test_multiple_anomalies_concatenated(self):
        metrics = [make_metrics(7)]
        health = {7: make_health(any_anomaly=True, spike=True, stall=True)}
        rows = prepare_process_table_data(metrics, [], health)
        self.assertIn("io_spike", rows[0]["status"])
        self.assertIn("io_stall", rows[0]["status"])

    def test_normal_when_no_health(self):
        metrics = [make_metrics(7)]
        rows = prepare_process_table_data(metrics, [], {})
        self.assertEqual(rows[0]["status"], "Normal")

    def test_missing_classification_displays_unknown(self):
        metrics = [make_metrics(7)]
        rows = prepare_process_table_data(metrics, [], {})
        self.assertEqual(rows[0]["classification"], "—")
        self.assertEqual(rows[0]["classification_raw"], "IDLE")

    def test_unavailable_process_handled(self):
        # Simulates a process exit mid-refresh: pids present but names gone.
        metrics = [make_metrics(9, name="gone")]
        rows = prepare_process_table_data(metrics, [], {})
        self.assertEqual(rows[0]["name"], "gone")
        self.assertEqual(rows[0]["pid"], "9")

    def test_malformed_metric_safe(self):
        rows = prepare_process_table_data([{"pid": 1, "name": None}], [], {})
        self.assertEqual(rows[0]["name"], "unknown")

    def test_long_name_truncated(self):
        metrics = [make_metrics(1, name="x" * 100)]
        rows = prepare_process_table_data(metrics, [], {})
        self.assertLessEqual(len(rows[0]["name"]), 24)
        self.assertEqual(rows[0]["name_raw"], "x" * 100)


# ===================================================================
# Section C – Classification scatter data
# ===================================================================

class TestPrepareClassificationScatterData(unittest.TestCase):
    def test_empty(self):
        data = prepare_classification_scatter_data([])
        self.assertEqual(data["total_points"], 0)
        self.assertEqual(data["series"], {})

    def test_points_grouped_by_class(self):
        classifications = [
            make_classification(1, name="a", cls="CPU_BOUND", cpu=80.0, io=1000.0),
            make_classification(2, name="b", cls="CPU_BOUND", cpu=90.0, io=2000.0),
            make_classification(3, name="c", cls="IO_BOUND", cpu=5.0, io=900000.0),
        ]
        data = prepare_classification_scatter_data(classifications)
        self.assertEqual(data["total_points"], 3)
        self.assertEqual(len(data["series"]["CPU_BOUND"]["x"]), 2)
        self.assertEqual(len(data["series"]["IO_BOUND"]["x"]), 1)
        self.assertEqual(data["series"]["CPU_BOUND"]["x"], [80.0, 90.0])
        self.assertEqual(data["series"]["IO_BOUND"]["y"], [900000.0])
        self.assertEqual(data["series"]["CPU_BOUND"]["names"], ["a", "b"])

    def test_unknown_class_goes_to_idle(self):
        classifications = [make_classification(1, cls="WEIRD")]
        data = prepare_classification_scatter_data(classifications)
        self.assertIn("IDLE", data["series"])
        self.assertNotIn("WEIRD", data["series"])

    def test_non_dict_entry_ignored(self):
        data = prepare_classification_scatter_data([None, "garbage", 42])
        self.assertEqual(data["total_points"], 0)


# ===================================================================
# Section D – Throughput history
# ===================================================================

class TestPrepareThroughputHistory(unittest.TestCase):
    def test_empty(self):
        data = prepare_throughput_history([])
        self.assertEqual(data, {"timestamps": [], "read": [], "write": [], "total": []})

    def test_series_built(self):
        history = [
            {"timestamp": 1.0, "read_bytes_per_sec": 100.0, "write_bytes_per_sec": 50.0,
             "total_io_bytes_per_sec": 150.0},
            {"timestamp": 2.0, "read_bytes_per_sec": 200.0, "write_bytes_per_sec": 60.0,
             "total_io_bytes_per_sec": 260.0},
        ]
        data = prepare_throughput_history(history)
        self.assertEqual(data["timestamps"], [1.0, 2.0])
        self.assertEqual(data["read"], [100.0, 200.0])
        self.assertEqual(data["write"], [50.0, 60.0])
        self.assertEqual(data["total"], [150.0, 260.0])

    def test_non_dict_entries_skipped(self):
        # None and strings are skipped; `{}` is still a dict so it yields
        # a single all-zero sample.
        data = prepare_throughput_history([None, {}, "x", make_metrics(1)])
        self.assertEqual(len(data["read"]), 2)

    def test_missing_fields_default_zero(self):
        data = prepare_throughput_history([{"timestamp": 1.0}])
        self.assertEqual(data["read"], [0.0])


# ===================================================================
# Section E – Anomaly display data
# ===================================================================

class TestPrepareAnomalyDisplayData(unittest.TestCase):
    def test_no_anomalies(self):
        rows = prepare_anomaly_display_data([1], [make_health(any_anomaly=False)], {})
        self.assertEqual(rows, [])

    def test_single_spike_row(self):
        pids = [7]
        health = [make_health(any_anomaly=True, spike=True, spike_severity="high",
                              spike_reason="I/O spike detected!")]
        class_map = {7: {"process_name": "db"}}
        rows = prepare_anomaly_display_data(pids, health, class_map)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["pid"], "7")
        self.assertEqual(row["process_name"], "db")
        self.assertEqual(row["severity"], "High")
        self.assertEqual(row["type"], "io_spike")
        self.assertEqual(row["reason"], "I/O spike detected!")
        self.assertIn("ratio=6.0", row["evidence"])

    def test_multiple_anomalies_flat(self):
        pids = [7]
        health = [make_health(any_anomaly=True, spike=True, stall=True)]
        rows = prepare_anomaly_display_data(pids, health, {})
        types = {r["type"] for r in rows}
        self.assertEqual(types, {"io_spike", "io_stall"})

    def test_multiple_processes(self):
        pids = [1, 2]
        health = [
            make_health(spike=True),
            make_health(shift=True),
        ]
        rows = prepare_anomaly_display_data(pids, health, {})
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["pid"] for r in rows}, {"1", "2"})
        self.assertEqual({r["type"] for r in rows}, {"io_spike", "rw_ratio_shift"})

    def test_missing_class_map_defaults_unknown(self):
        rows = prepare_anomaly_display_data([7], [make_health(any_anomaly=True, spike=True)], None)
        self.assertEqual(rows[0]["process_name"], "unknown")

    def test_non_dict_health_skipped(self):
        rows = prepare_anomaly_display_data([1, 2], [None, "garbage"], {})
        self.assertEqual(rows, [])

    def test_non_numeric_pid_safe(self):
        rows = prepare_anomaly_display_data(["abc"], [make_health(any_anomaly=True, spike=True)], {})
        self.assertEqual(rows[0]["pid"], "abc")

    def test_default_reason_when_missing(self):
        health = make_health(any_anomaly=True, spike=True, spike_reason="")
        health["io_spike"]["reason"] = ""
        rows = prepare_anomaly_display_data([7], [health], {})
        self.assertEqual(rows[0]["reason"], "")


# ===================================================================
# Evidence extraction
# ===================================================================

class TestExtractAnomalyEvidence(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(extract_anomaly_evidence({}), "")

    def test_known_fields_present(self):
        evidence = extract_anomaly_evidence(
            {"current_rate": 60000.0, "baseline_rate": 10000.0, "ratio": 6.0}
        )
        self.assertIn("current_rate=60000.0", evidence)
        self.assertIn("baseline_rate=10000.0", evidence)
        self.assertIn("ratio=6.0", evidence)

    def test_none_fields_excluded(self):
        evidence = extract_anomaly_evidence({"current_rate": None, "ratio": None})
        self.assertEqual(evidence, "")

    def test_unknown_fields_ignored(self):
        evidence = extract_anomaly_evidence({"foo": 1, "bar": 2})
        self.assertEqual(evidence, "")

    def test_commas_join_multiple(self):
        evidence = extract_anomaly_evidence({"ratio": 6.0, "silent_observations": 3})
        self.assertEqual(evidence, "ratio=6.0, silent_observations=3")


# ===================================================================
# Section F – Scheduling display data
# ===================================================================

def make_scheduling_result():
    return {
        "observed_processes": [
            {"pid": 1, "name": "a", "total_io_bytes_per_sec": 1000.0,
             "classification": "IO_BOUND"},
        ],
        "simulated_request_queue": [10, 55, 40, 90],
        "simulation_note": "Simulated disk request workload derived from observed process I/O activity.",
        "scheduling_analysis": {
            "request_count": 4,
            "disk_size": 200,
            "head_position": 0,
            "direction": "right",
            "results": {
                "FCFS": {"algorithm": "FCFS", "request_count": 4, "total_head_movement": 330},
                "SSTF": {"algorithm": "SSTF", "request_count": 4, "total_head_movement": 135},
                "SCAN": {"algorithm": "SCAN", "request_count": 4, "total_head_movement": 200},
                "C-SCAN": {"algorithm": "C-SCAN", "request_count": 4, "total_head_movement": 390},
            },
            "total_head_movements": {
                "FCFS": 330, "SSTF": 135, "SCAN": 200, "C-SCAN": 390,
            },
            "recommended_algorithm": "SSTF",
            "reason": "SSTF minimizes total head movement (135 cylinders).",
        },
    }


class TestPrepareSchedulingDisplayData(unittest.TestCase):
    def test_none_result(self):
        data = prepare_scheduling_display_data(None)
        self.assertEqual(data["request_count"], 0)
        self.assertEqual(data["algorithms"], {})
        self.assertEqual(data["recommended"], "—")
        self.assertIn("No telemetry", data["recommendation_reason"])

    def test_non_dict_result(self):
        data = prepare_scheduling_display_data("bad")
        self.assertEqual(data["request_count"], 0)
        self.assertEqual(data["recommended"], "—")

    def test_all_four_algorithms(self):
        data = prepare_scheduling_display_data(make_scheduling_result())
        self.assertEqual(set(data["algorithms"].keys()),
                         {"FCFS", "SSTF", "SCAN", "C-SCAN"})

    def test_head_movements_extracted(self):
        data = prepare_scheduling_display_data(make_scheduling_result())
        self.assertEqual(data["algorithms"]["FCFS"]["head_movement"], 330)
        self.assertEqual(data["algorithms"]["SSTF"]["head_movement"], 135)
        self.assertEqual(data["algorithms"]["SCAN"]["head_movement"], 200)
        self.assertEqual(data["algorithms"]["C-SCAN"]["head_movement"], 390)

    def test_request_counts_extracted(self):
        data = prepare_scheduling_display_data(make_scheduling_result())
        for name in ("FCFS", "SSTF", "SCAN", "C-SCAN"):
            self.assertEqual(data["algorithms"][name]["request_count"], 4)

    def test_recommendation(self):
        data = prepare_scheduling_display_data(make_scheduling_result())
        self.assertEqual(data["recommended"], "SSTF")
        self.assertIn("minimizes", data["recommendation_reason"])

    def test_request_count_top_level(self):
        data = prepare_scheduling_display_data(make_scheduling_result())
        self.assertEqual(data["request_count"], 4)

    def test_simulation_note_preserved(self):
        data = prepare_scheduling_display_data(make_scheduling_result())
        self.assertIn("Simulated", data["simulation_note"])

    def test_missing_movements_default_int(self):
        result = make_scheduling_result()
        result["scheduling_analysis"]["total_head_movements"] = {}
        data = prepare_scheduling_display_data(result)
        for name in ("FCFS", "SSTF", "SCAN", "C-SCAN"):
            self.assertEqual(data["algorithms"][name]["head_movement"], 0)


# ===================================================================
# Section G – Explainability
# ===================================================================

class TestPrepareExplanation(unittest.TestCase):
    def test_no_data(self):
        text = prepare_explanation("classification", None)
        self.assertIn("No data selected", text)

    def test_unknown_kind(self):
        self.assertEqual(prepare_explanation("bogus", {}), "No explanation available.")

    def test_classification_uses_reason(self):
        text = prepare_explanation("classification", {
            "classification": "IO_BOUND",
            "reason": "Process is classified as IO_BOUND because I/O activity "
                      "is high relative to CPU utilization.",
            "confidence": 0.85,
        })
        self.assertIn("IO_BOUND", text)
        self.assertIn("high relative to CPU", text)
        self.assertIn("0.85", text)

    def test_classification_builds_default_from_metrics(self):
        text = prepare_explanation("classification", {
            "classification": "CPU_BOUND",
            "cpu_percent": 90.0,
            "total_io_bytes_per_sec": 100.0,
            "reason": "",
            "confidence": None,
        })
        self.assertIn("CPU_BOUND", text)
        self.assertIn("90.0%", text)
        self.assertNotIn("confidence", text)

    def test_spike_anomaly_reason(self):
        text = prepare_explanation("anomaly", {
            "type": "io_spike", "severity": "high",
            "reason": "I/O spike detected: current rate (60000 B/s) is 6.0x the baseline.",
        })
        self.assertIn("I/O spike detected", text)
        self.assertIn("High", text)

    def test_spike_anomaly_rate_ratio(self):
        health = make_health(any_anomaly=True, spike=True, spike_reason="")
        text = prepare_explanation("anomaly", health["io_spike"])
        self.assertIn("6.0x", text)
        self.assertIn("Evidence:", text)

    def test_stall_anomaly(self):
        health = make_health(stall=True)
        # Clear the canned reason so the default human-readable branch runs.
        health["io_stall"]["reason"] = ""
        text = prepare_explanation("anomaly", health["io_stall"])
        self.assertIn("STALL", text.upper())
        self.assertIn("near-zero", text)

    def test_stall_anomaly_real_reason_kept(self):
        health = make_health(stall=True)
        health["io_stall"]["reason"] = (
            "I/O stall detected: process was previously active (200000 B/s)"
            " but has shown near-zero I/O for 4 observations."
        )
        text = prepare_explanation("anomaly", health["io_stall"])
        self.assertIn("I/O stall detected", text)
        self.assertIn("200000 B/s", text)

    def test_sustained_anomaly(self):
        health = make_health(any_anomaly=True, sustained=True)
        text = prepare_explanation("anomaly", health["sustained_high_io"])
        self.assertIn("SUSTAINED", text.upper())

    def test_ratio_shift_anomaly(self):
        health = make_health(any_anomaly=True, shift=True)
        text = prepare_explanation("anomaly", health["rw_ratio_shift"])
        self.assertIn("RATIO", text.upper())

    def test_scheduling_explanation_uses_reason(self):
        text = prepare_explanation("scheduling", {
            "recommended": "SSTF",
            "recommendation_reason": "SSTF minimizes total head movement (135 cylinders).",
        })
        self.assertEqual(text, "SSTF minimizes total head movement (135 cylinders).")

    def test_scheduling_no_reason_default(self):
        text = prepare_explanation("scheduling", {"recommended": "SSTF",
                                                  "recommendation_reason": ""})
        self.assertIn("SSTF", text)


# ===================================================================
# Integrated pipeline (module inputs → display data)
# ===================================================================

class TestIOPulsePipeline(unittest.TestCase):
    def test_end_to_end_all_sections(self):
        metrics = [
            make_metrics(1, name="a", cpu=90.0, read=100.0, write=100.0),
            make_metrics(2, name="b", cpu=5.0, read=800000.0, write=200000.0),
            make_metrics(3, name="c", cpu=30.0, read=300000.0, write=300000.0),
        ]
        classifications = [
            make_classification(1, name="a", cls="CPU_BOUND", cpu=90.0),
            make_classification(2, name="b", cls="IO_BOUND", io=1000000.0),
            make_classification(3, name="c", cls="BALANCED"),
        ]
        health = [
            make_health(any_anomaly=True, spike=True),
            make_health(any_anomaly=False),
            make_health(any_anomaly=False),
        ]
        class_map = {c["pid"]: c for c in classifications}

        overview = prepare_overview_data(metrics, classifications, health)
        self.assertEqual(overview["total_processes"], 3)
        self.assertEqual(overview["cpu_bound_count"], 1)
        self.assertEqual(overview["io_bound_count"], 1)
        self.assertEqual(overview["balanced_count"], 1)
        self.assertEqual(overview["active_anomalies"], 1)

        rows = prepare_process_table_data(metrics, classifications, {
            1: health[0], 2: health[1], 3: health[2],
        })
        self.assertEqual(len(rows), 3)
        statuses = {r["pid"]: r["status"] for r in rows}
        self.assertIn("io_spike", statuses["1"])

        anomalies = prepare_anomaly_display_data([1, 2, 3], health, class_map)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["type"], "io_spike")
        self.assertEqual(anomalies[0]["process_name"], "a")

    def test_empty_telemetry_full_pipeline(self):
        overview = prepare_overview_data([], [], [])
        self.assertEqual(overview["total_processes"], 0)
        self.assertEqual(overview["active_anomalies"], 0)
        self.assertEqual(prepare_process_table_data([], [], {}), [])
        self.assertEqual(prepare_classification_scatter_data([])["total_points"], 0)
        self.assertEqual(prepare_anomaly_display_data([], [], {}), [])
        data = prepare_scheduling_display_data(None)
        self.assertEqual(data["recommended"], "—")


if __name__ == "__main__":
    unittest.main()