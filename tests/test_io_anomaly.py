"""Tests for intelligence/io_anomaly.py — I/O Anomaly Detection.

Covers all four detectors and the batch analyze_io_health() helper.
All tests use plain metric dictionaries — no psutil or real processes.
"""

from __future__ import annotations

import unittest

from intelligence.io_anomaly import (
    SUSTAINED_CONSECUTIVE,
    RATIO_SHIFT_MIN_HISTORY,
    RATIO_SHIFT_MULTIPLIER,
    analyze_io_health,
    detect_io_spike,
    detect_io_stall,
    detect_rw_ratio_shift,
    detect_sustained_high_io,
)


# ===================================================================
# Helpers
# ===================================================================

def _make_metrics(
    total_io_bytes_per_sec: float = 0.0,
    read_bytes_per_sec: float = 0.0,
    write_bytes_per_sec: float = 0.0,
    read_write_ratio: float = 0.0,
    pid: int = 100,
) -> dict:
    return {
        "pid": pid,
        "name": "test_proc",
        "total_io_bytes_per_sec": total_io_bytes_per_sec,
        "read_bytes_per_sec": read_bytes_per_sec,
        "write_bytes_per_sec": write_bytes_per_sec,
        "read_write_ratio": read_write_ratio,
    }


def _stable_history(
    rate: float = 100_000.0,
    count: int = 5,
    rw_ratio: float = 1.0,
) -> list[dict]:
    """Create a stable history at a fixed rate."""
    return [_make_metrics(total_io_bytes_per_sec=rate, read_write_ratio=rw_ratio) for _ in range(count)]


# ===================================================================
# detect_io_spike tests
# ===================================================================

class TestIOSpike(unittest.TestCase):
    def test_no_history(self):
        result = detect_io_spike([])
        self.assertFalse(result["anomaly"])
        self.assertEqual(result["type"], "none")

    def test_insufficient_history(self):
        result = detect_io_spike([_make_metrics(total_io_bytes_per_sec=1000)])
        self.assertFalse(result["anomaly"])

    def test_stable_rate_no_spike(self):
        history = _stable_history(rate=100_000, count=5)
        result = detect_io_spike(history)
        self.assertFalse(result["anomaly"])
        self.assertEqual(result["type"], "none")

    def test_clear_spike(self):
        history = _stable_history(rate=100_000, count=4)
        history.append(_make_metrics(total_io_bytes_per_sec=1_000_000))  # 10× spike
        result = detect_io_spike(history)
        self.assertTrue(result["anomaly"])
        self.assertEqual(result["type"], "io_spike")
        self.assertGreater(result["ratio"], 5.0)

    def test_spike_ratio_computed(self):
        history = _stable_history(rate=100_000, count=4)
        history.append(_make_metrics(total_io_bytes_per_sec=500_000))  # 5× spike
        result = detect_io_spike(history)
        self.assertTrue(result["anomaly"])
        self.assertAlmostEqual(result["baseline_rate"], 100_000.0, places=0)
        self.assertAlmostEqual(result["current_rate"], 500_000.0, places=0)

    def test_below_min_rate_no_spike(self):
        history = _stable_history(rate=500, count=4)  # below min_rate of 10k
        history.append(_make_metrics(total_io_bytes_per_sec=50_000))  # 100× but baseline too low
        result = detect_io_spike(history)
        self.assertFalse(result["anomaly"])

    def test_severity_scales_with_ratio(self):
        # 5× → low, 10× → high, 15× → critical
        history_5x = _stable_history(rate=100_000, count=4)
        history_5x.append(_make_metrics(total_io_bytes_per_sec=500_000))

        history_10x = _stable_history(rate=100_000, count=4)
        history_10x.append(_make_metrics(total_io_bytes_per_sec=1_000_000))

        history_15x = _stable_history(rate=100_000, count=4)
        history_15x.append(_make_metrics(total_io_bytes_per_sec=1_500_000))

        r5 = detect_io_spike(history_5x)
        r10 = detect_io_spike(history_10x)
        r15 = detect_io_spike(history_15x)

        severity_order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        self.assertGreater(severity_order[r10["severity"]], severity_order[r5["severity"]])
        self.assertGreater(severity_order[r15["severity"]], severity_order[r10["severity"]])

    def test_custom_multiplier(self):
        history = _stable_history(rate=100_000, count=4)
        history.append(_make_metrics(total_io_bytes_per_sec=300_000))  # 3×
        result = detect_io_spike(history, spike_multiplier=2.0)
        self.assertTrue(result["anomaly"])

    def test_non_dict_in_history(self):
        """Non-dict entries are treated as having zero rate."""
        history = [_make_metrics(total_io_bytes_per_sec=100_000)] * 3
        history.append("invalid")
        history.append(_make_metrics(total_io_bytes_per_sec=1_000_000))
        result = detect_io_spike(history)
        # "invalid" gets rate 0, so baseline average = (100k+100k+100k+0)/4 = 75k
        # 1M / 75k = 13.3× → spike
        self.assertTrue(result["anomaly"])

    def test_result_structure(self):
        result = detect_io_spike(_stable_history())
        self.assertIn("anomaly", result)
        self.assertIn("type", result)
        self.assertIn("severity", result)
        self.assertIn("reason", result)
        self.assertIn("current_rate", result)
        self.assertIn("baseline_rate", result)
        self.assertIn("ratio", result)
        self.assertIn("num_observations", result)
        self.assertIn("thresholds", result)
        self.assertIn("spike_multiplier", result["thresholds"])


# ===================================================================
# detect_io_stall tests
# ===================================================================

class TestIOStall(unittest.TestCase):
    def test_no_history(self):
        result = detect_io_stall([])
        self.assertFalse(result["anomaly"])

    def test_insufficient_history(self):
        history = [_make_metrics(total_io_bytes_per_sec=100_000)] * 2
        result = detect_io_stall(history)
        self.assertFalse(result["anomaly"])

    def test_active_process_no_stall(self):
        history = _stable_history(rate=100_000, count=6)
        result = detect_io_stall(history)
        self.assertFalse(result["anomaly"])

    def test_clear_stall(self):
        history = _stable_history(rate=100_000, count=3)
        # 3 consecutive near-zero observations → stall
        history.extend([
            _make_metrics(total_io_bytes_per_sec=0.0),
            _make_metrics(total_io_bytes_per_sec=0.0),
            _make_metrics(total_io_bytes_per_sec=0.0),
        ])
        result = detect_io_stall(history)
        self.assertTrue(result["anomaly"])
        self.assertEqual(result["type"], "io_stall")
        self.assertEqual(result["silent_observations"], 3)

    def test_stall_below_min_previous_rate(self):
        """Process was never very active → no stall."""
        history = _stable_history(rate=10_000, count=3)  # below default 50k
        history.extend([
            _make_metrics(total_io_bytes_per_sec=0.0),
            _make_metrics(total_io_bytes_per_sec=0.0),
            _make_metrics(total_io_bytes_per_sec=0.0),
        ])
        result = detect_io_stall(history)
        self.assertFalse(result["anomaly"])

    def test_stall_severity_scales(self):
        # Higher last active rate → higher severity
        base = [_make_metrics(total_io_bytes_per_sec=0.0)] * 3
        # low severity: last rate = 50k (= min_previous_rate)
        history_low = [_make_metrics(total_io_bytes_per_sec=50_000)] + base
        # critical severity: last rate = 500k (10× min)
        history_crit = [_make_metrics(total_io_bytes_per_sec=500_000)] + base

        r_low = detect_io_stall(history_low)
        r_crit = detect_io_stall(history_crit)
        severity_order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        self.assertGreater(severity_order[r_crit["severity"]], severity_order[r_low["severity"]])

    def test_zero_rate_below_threshold(self):
        """Rate of 50 B/s is below zero_threshold of 100 → counts as zero."""
        history = _stable_history(rate=100_000, count=3)
        history.extend([
            _make_metrics(total_io_bytes_per_sec=50.0),
            _make_metrics(total_io_bytes_per_sec=50.0),
            _make_metrics(total_io_bytes_per_sec=50.0),
        ])
        result = detect_io_stall(history)
        self.assertTrue(result["anomaly"])

    def test_rate_just_above_zero_threshold(self):
        """Rate of 150 B/s is above zero_threshold → not zero."""
        history = _stable_history(rate=100_000, count=3)
        history.extend([
            _make_metrics(total_io_bytes_per_sec=150.0),
            _make_metrics(total_io_bytes_per_sec=150.0),
            _make_metrics(total_io_bytes_per_sec=150.0),
        ])
        result = detect_io_stall(history)
        self.assertFalse(result["anomaly"])

    def test_result_structure(self):
        result = detect_io_stall(_stable_history())
        self.assertIn("anomaly", result)
        self.assertIn("type", result)
        self.assertIn("severity", result)
        self.assertIn("reason", result)
        self.assertIn("last_active_rate", result)
        self.assertIn("silent_observations", result)
        self.assertIn("thresholds", result)


# ===================================================================
# detect_sustained_high_io tests
# ===================================================================

class TestSustainedHighIO(unittest.TestCase):
    def test_no_history(self):
        result = detect_sustained_high_io([])
        self.assertFalse(result["anomaly"])

    def test_insufficient_history(self):
        history = [_make_metrics(total_io_bytes_per_sec=10_000_000)] * 3
        result = detect_sustained_high_io(history)
        self.assertFalse(result["anomaly"])

    def test_no_sustained_high(self):
        history = _stable_history(rate=1_000_000, count=SUSTAINED_CONSECUTIVE)
        result = detect_sustained_high_io(history)
        self.assertFalse(result["anomaly"])

    def test_clear_sustained_high(self):
        history = [_make_metrics(total_io_bytes_per_sec=10_000_000)] * SUSTAINED_CONSECUTIVE
        result = detect_sustained_high_io(history)
        self.assertTrue(result["anomaly"])
        self.assertEqual(result["type"], "sustained_high_io")
        self.assertEqual(result["consecutive_high_count"], SUSTAINED_CONSECUTIVE)

    def test_sustained_high_interrupted(self):
        """One low observation breaks the streak."""
        history = [_make_metrics(total_io_bytes_per_sec=10_000_000)] * (SUSTAINED_CONSECUTIVE + 1)
        history[-2] = _make_metrics(total_io_bytes_per_sec=1000)  # breaks streak
        result = detect_sustained_high_io(history)
        self.assertFalse(result["anomaly"])

    def test_average_rate_computed(self):
        rates = [5_000_000, 6_000_000, 7_000_000, 8_000_000, 9_000_000]
        history = [_make_metrics(total_io_bytes_per_sec=r) for r in rates]
        result = detect_sustained_high_io(history)
        self.assertTrue(result["anomaly"])
        self.assertAlmostEqual(result["average_high_rate"], 7_000_000.0, places=0)

    def test_severity_scales(self):
        history_med = [_make_metrics(total_io_bytes_per_sec=10_000_000)] * (SUSTAINED_CONSECUTIVE + 2)
        history_crit = [_make_metrics(total_io_bytes_per_sec=10_000_000)] * (SUSTAINED_CONSECUTIVE * 3)

        r_med = detect_sustained_high_io(history_med)
        r_crit = detect_sustained_high_io(history_crit)
        severity_order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        self.assertGreater(severity_order[r_crit["severity"]], severity_order[r_med["severity"]])

    def test_custom_threshold(self):
        history = [_make_metrics(total_io_bytes_per_sec=2_000_000)] * 5
        result = detect_sustained_high_io(history, high_rate=1_000_000, consecutive=5)
        self.assertTrue(result["anomaly"])

    def test_result_structure(self):
        result = detect_sustained_high_io(_stable_history())
        self.assertIn("anomaly", result)
        self.assertIn("type", result)
        self.assertIn("severity", result)
        self.assertIn("reason", result)
        self.assertIn("consecutive_high_count", result)
        self.assertIn("average_high_rate", result)
        self.assertIn("thresholds", result)


# ===================================================================
# detect_rw_ratio_shift tests
# ===================================================================

class TestRWRatioShift(unittest.TestCase):
    def test_no_history(self):
        result = detect_rw_ratio_shift([])
        self.assertFalse(result["anomaly"])

    def test_insufficient_history(self):
        history = [_make_metrics(read_write_ratio=1.0)] * 3
        result = detect_rw_ratio_shift(history)
        self.assertFalse(result["anomaly"])

    def test_stable_ratio_no_shift(self):
        history = [_make_metrics(read_write_ratio=1.0)] * (RATIO_SHIFT_MIN_HISTORY + 1)
        result = detect_rw_ratio_shift(history)
        self.assertFalse(result["anomaly"])

    def test_clear_shift(self):
        baseline_count = RATIO_SHIFT_MIN_HISTORY
        history = [_make_metrics(read_write_ratio=1.0)] * baseline_count
        history.append(_make_metrics(read_write_ratio=10.0))  # 10× shift
        result = detect_rw_ratio_shift(history)
        self.assertTrue(result["anomaly"])
        self.assertEqual(result["type"], "rw_ratio_shift")
        self.assertGreater(result["ratio_of_ratios"], RATIO_SHIFT_MULTIPLIER)

    def test_shift_to_zero_ratio(self):
        """Ratio going from 1.0 to 0.01 (below min_ratio) should not trigger."""
        history = [_make_metrics(read_write_ratio=1.0)] * (RATIO_SHIFT_MIN_HISTORY + 1)
        history.append(_make_metrics(read_write_ratio=0.001))
        result = detect_rw_ratio_shift(history)
        self.assertFalse(result["anomaly"])

    def test_baseline_all_below_min_ratio(self):
        """If all baseline ratios are below min_ratio, no detection."""
        history = [_make_metrics(read_write_ratio=0.01)] * (RATIO_SHIFT_MIN_HISTORY + 1)
        result = detect_rw_ratio_shift(history)
        self.assertFalse(result["anomaly"])

    def test_inf_ratio_handled(self):
        """Infinite ratio (write=0, read>0) should be handled gracefully."""
        history = [_make_metrics(read_write_ratio=float("inf"))] * (RATIO_SHIFT_MIN_HISTORY + 1)
        history.append(_make_metrics(read_write_ratio=1.0))
        result = detect_rw_ratio_shift(history)
        self.assertTrue(result["anomaly"])

    def test_severity_scales(self):
        baseline_count = RATIO_SHIFT_MIN_HISTORY
        history_low = [_make_metrics(read_write_ratio=1.0)] * baseline_count
        history_low.append(_make_metrics(read_write_ratio=5.0))

        history_high = [_make_metrics(read_write_ratio=1.0)] * baseline_count
        history_high.append(_make_metrics(read_write_ratio=50.0))

        r_low = detect_rw_ratio_shift(history_low)
        r_high = detect_rw_ratio_shift(history_high)
        severity_order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        self.assertGreater(severity_order[r_high["severity"]], severity_order[r_low["severity"]])

    def test_result_structure(self):
        result = detect_rw_ratio_shift(_stable_history())
        self.assertIn("anomaly", result)
        self.assertIn("type", result)
        self.assertIn("severity", result)
        self.assertIn("reason", result)
        self.assertIn("current_ratio", result)
        self.assertIn("baseline_ratio", result)
        self.assertIn("ratio_of_ratios", result)
        self.assertIn("thresholds", result)


# ===================================================================
# analyze_io_health tests
# ===================================================================

class TestAnalyzeIOHealth(unittest.TestCase):
    def test_returns_all_keys(self):
        result = analyze_io_health([])
        self.assertIn("io_spike", result)
        self.assertIn("io_stall", result)
        self.assertIn("sustained_high_io", result)
        self.assertIn("rw_ratio_shift", result)
        self.assertIn("any_anomaly", result)
        self.assertIn("most_severe", result)

    def test_no_anomaly_on_empty_history(self):
        result = analyze_io_health([])
        self.assertFalse(result["any_anomaly"])
        self.assertEqual(result["most_severe"], "none")

    def test_spike_detected_in_batch(self):
        history = _stable_history(rate=100_000, count=4)
        history.append(_make_metrics(total_io_bytes_per_sec=1_000_000))
        result = analyze_io_health(history)
        self.assertTrue(result["any_anomaly"])
        self.assertTrue(result["io_spike"]["anomaly"])

    def test_stall_detected_in_batch(self):
        history = _stable_history(rate=100_000, count=3)
        history.extend([
            _make_metrics(total_io_bytes_per_sec=0.0),
            _make_metrics(total_io_bytes_per_sec=0.0),
            _make_metrics(total_io_bytes_per_sec=0.0),
        ])
        result = analyze_io_health(history)
        self.assertTrue(result["any_anomaly"])
        self.assertTrue(result["io_stall"]["anomaly"])

    def test_sustained_high_detected_in_batch(self):
        history = [_make_metrics(total_io_bytes_per_sec=10_000_000)] * SUSTAINED_CONSECUTIVE
        result = analyze_io_health(history)
        self.assertTrue(result["any_anomaly"])
        self.assertTrue(result["sustained_high_io"]["anomaly"])

    def test_most_severe_picks_highest(self):
        """When multiple anomalies, most_severe reflects the highest."""
        # Create a scenario with both spike AND stall
        history = _stable_history(rate=100_000, count=4)
        history.append(_make_metrics(total_io_bytes_per_sec=1_000_000))  # spike

        result = analyze_io_health(history)
        self.assertTrue(result["io_spike"]["anomaly"])

    def test_custom_thresholds_propagated(self):
        """Custom thresholds are forwarded to each detector."""
        history = _stable_history(rate=100_000, count=4)
        history.append(_make_metrics(total_io_bytes_per_sec=300_000))
        result = analyze_io_health(history, spike_multiplier=2.0)
        self.assertTrue(result["io_spike"]["anomaly"])

    def test_empty_history_all_none(self):
        result = analyze_io_health([])
        for key in ["io_spike", "io_stall", "sustained_high_io", "rw_ratio_shift"]:
            self.assertEqual(result[key]["type"], "none")


# ===================================================================
# Edge cases and robustness
# ===================================================================

class TestEdgeCases(unittest.TestCase):
    def test_none_values_in_metrics(self):
        """None values in history should not crash detectors."""
        history = [None] * 4
        history[-1] = _make_metrics(total_io_bytes_per_sec=1000)
        result = detect_io_spike(history)
        # None entries get rate 0 via _safe_rate. Baseline avg = 0.
        # baseline_rate (0) < min_rate → no spike.
        self.assertFalse(result["anomaly"])

    def test_negative_rates_clamped(self):
        """Negative rates should be treated as zero."""
        history = _stable_history(rate=100_000, count=4)
        history.append(_make_metrics(total_io_bytes_per_sec=-5000))
        result = detect_io_spike(history)
        # Negative gets treated as 0 — ratio = 0/100000 = 0 → no spike
        self.assertFalse(result["anomaly"])

    def test_empty_dict_metrics(self):
        """Empty dicts have zero rates — no spike since baseline is also zero."""
        history = [{}] * 4
        history.append(_make_metrics(total_io_bytes_per_sec=1_000_000))
        result = detect_io_spike(history)
        # All entries have rate 0 except last. Baseline avg = 0.
        # baseline_rate (0) < min_rate (10000) → no spike.
        self.assertFalse(result["anomaly"])

    def test_very_large_rates(self):
        """Extremely large rates should not cause overflow."""
        history = _stable_history(rate=1e15, count=4)
        history.append(_make_metrics(total_io_bytes_per_sec=1e16))
        result = detect_io_spike(history)
        self.assertTrue(result["anomaly"])

    def test_all_detectors_on_normal_history(self):
        """A normal, stable history should trigger no anomalies."""
        history = _stable_history(rate=500_000, count=10, rw_ratio=1.5)
        result = analyze_io_health(history)
        self.assertFalse(result["any_anomaly"])

    def test_detectors_handle_string_history(self):
        """Non-list input should not crash."""
        result = detect_io_spike("invalid")
        self.assertFalse(result["anomaly"])

        result = detect_io_stall("invalid")
        self.assertFalse(result["anomaly"])

        result = detect_sustained_high_io("invalid")
        self.assertFalse(result["anomaly"])

        result = detect_rw_ratio_shift("invalid")
        self.assertFalse(result["anomaly"])


if __name__ == "__main__":
    unittest.main()
