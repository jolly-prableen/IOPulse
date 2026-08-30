"""
tests/test_io_metrics.py – Unit tests for intelligence/io_metrics.py
IOPulse – Phase 1: Process-Level I/O Telemetry

These tests verify:
  - Cumulative counter reading (collect_process_io)
  - Rate computation from cumulative deltas
  - Read/write ratio edge cases
  - First observation returns None (no rates yet)
  - Zero elapsed time handling
  - Zero I/O baseline handling
  - Missing I/O information (AccessDenied, NoSuchProcess, ZombieProcess)
  - Process termination between samples
  - Bounded history
  - Collector clear/reset
  - collect_all integration

All psutil calls are mocked so tests are deterministic and platform-independent.
"""

import unittest
from unittest.mock import MagicMock, patch

import psutil

from intelligence.io_metrics import (
    ProcessIOCollector,
    _compute_rates,
    _safe_float,
    _safe_int,
    collect_process_io,
)


# ---------------------------------------------------------------------------
# Helpers: mock psutil objects
# ---------------------------------------------------------------------------

def _make_io_counters(read_bytes=0, write_bytes=0, read_count=0, write_count=0):
    """Create a mock io_counters result."""
    io = MagicMock()
    io.read_bytes = read_bytes
    io.write_bytes = write_bytes
    io.read_count = read_count
    io.write_count = write_count
    return io


def _make_process(pid=100, name="test_proc", status="running",
                  io_counters_value=None, io_counters_raises=None):
    """Create a mock psutil.Process."""
    proc = MagicMock()
    proc.pid = pid
    proc.name.return_value = name
    proc.status.return_value = status
    proc.cpu_percent.return_value = 10.0
    proc.memory_percent.return_value = 5.0

    if io_counters_raises is not None:
        proc.io_counters.side_effect = io_counters_raises
    elif io_counters_value is not None:
        proc.io_counters.return_value = io_counters_value
    else:
        proc.io_counters.return_value = _make_io_counters()

    # oneshot() as a context manager
    proc.oneshot.return_value.__enter__ = MagicMock(return_value=None)
    proc.oneshot.return_value.__exit__ = MagicMock(return_value=False)

    return proc


# ===================================================================
# Test: _safe_float / _safe_int helpers
# ===================================================================

class TestSafeHelpers(unittest.TestCase):
    def test_safe_float_valid(self):
        self.assertEqual(_safe_float(42), 42.0)

    def test_safe_float_none(self):
        self.assertEqual(_safe_float(None), 0.0)

    def test_safe_float_string(self):
        self.assertEqual(_safe_float("bad"), 0.0)

    def test_safe_float_nan(self):
        self.assertEqual(_safe_float(float("nan")), 0.0)

    def test_safe_float_inf(self):
        self.assertEqual(_safe_float(float("inf")), 0.0)

    def test_safe_float_custom_default(self):
        self.assertEqual(_safe_float(None, -1.0), -1.0)

    def test_safe_int_valid(self):
        self.assertEqual(_safe_int(42), 42)

    def test_safe_int_none(self):
        self.assertEqual(_safe_int(None), 0)

    def test_safe_int_string(self):
        self.assertEqual(_safe_int("bad"), 0)

    def test_safe_int_custom_default(self):
        self.assertEqual(_safe_int(None, -1), -1)


# ===================================================================
# Test: _compute_rates
# ===================================================================

class TestComputeRates(unittest.TestCase):
    def test_normal_rate(self):
        """1000 bytes read and 500 bytes written over 1 second."""
        rbps, wbps, total, ratio = _compute_rates(
            prev_read_bytes=0, prev_write_bytes=0,
            curr_read_bytes=1000, curr_write_bytes=500,
            elapsed=1.0,
        )
        self.assertAlmostEqual(rbps, 1000.0)
        self.assertAlmostEqual(wbps, 500.0)
        self.assertAlmostEqual(total, 1500.0)
        self.assertAlmostEqual(ratio, 2.0)

    def test_zero_elapsed(self):
        """Zero elapsed time returns zero rates (division by zero guarded)."""
        rbps, wbps, total, ratio = _compute_rates(0, 0, 1000, 500, 0.0)
        self.assertEqual(rbps, 0.0)
        self.assertEqual(wbps, 0.0)
        self.assertEqual(total, 0.0)
        self.assertEqual(ratio, 0.0)

    def test_negative_elapsed(self):
        """Negative elapsed time returns zero rates."""
        rbps, wbps, total, ratio = _compute_rates(0, 0, 1000, 500, -1.0)
        self.assertEqual(rbps, 0.0)
        self.assertEqual(wbps, 0.0)

    def test_zero_total_io(self):
        """No I/O at all yields zero ratio."""
        rbps, wbps, total, ratio = _compute_rates(100, 200, 100, 200, 1.0)
        self.assertEqual(rbps, 0.0)
        self.assertEqual(wbps, 0.0)
        self.assertEqual(total, 0.0)
        self.assertEqual(ratio, 0.0)

    def test_write_zero_read_positive(self):
        """Write is 0 but read is positive → inf ratio (no crash)."""
        rbps, wbps, total, ratio = _compute_rates(0, 0, 1000, 0, 1.0)
        self.assertAlmostEqual(rbps, 1000.0)
        self.assertEqual(wbps, 0.0)
        self.assertEqual(ratio, float("inf"))

    def test_increasing_cumulative_counters(self):
        """Verify correct delta when counters increase between observations."""
        rbps, wbps, _, _ = _compute_rates(
            prev_read_bytes=5000, prev_write_bytes=3000,
            curr_read_bytes=7000, curr_write_bytes=4000,
            elapsed=2.0,
        )
        # delta_read = 2000, delta_write = 1000, elapsed = 2.0
        self.assertAlmostEqual(rbps, 1000.0)
        self.assertAlmostEqual(wbps, 500.0)

    def test_counters_decrease_returns_zero(self):
        """If counters somehow decrease, delta is clamped to 0."""
        rbps, wbps, total, _ = _compute_rates(
            prev_read_bytes=5000, prev_write_bytes=3000,
            curr_read_bytes=4000, curr_write_bytes=2000,
            elapsed=1.0,
        )
        self.assertEqual(rbps, 0.0)
        self.assertEqual(wbps, 0.0)
        self.assertEqual(total, 0.0)

    def test_small_elapsed_high_throughput(self):
        """Rate with a very small but positive elapsed time."""
        rbps, _, _, _ = _compute_rates(0, 0, 1_000_000, 0, 0.001)
        self.assertAlmostEqual(rbps, 1_000_000_000.0)


# ===================================================================
# Test: collect_process_io
# ===================================================================

class TestCollectProcessIO(unittest.TestCase):
    def test_valid_process_io_metrics(self):
        """Valid process returns all expected keys."""
        io = _make_io_counters(read_bytes=1024, write_bytes=2048,
                               read_count=10, write_count=20)
        proc = _make_process(pid=42, name="myapp", io_counters_value=io)

        result = collect_process_io(proc)

        self.assertIsNotNone(result)
        self.assertEqual(result["pid"], 42)
        self.assertEqual(result["name"], "myapp")
        self.assertEqual(result["state"], "running")
        self.assertEqual(result["read_bytes"], 1024)
        self.assertEqual(result["write_bytes"], 2048)
        self.assertEqual(result["read_count"], 10)
        self.assertEqual(result["write_count"], 20)

    def test_zero_io_baseline(self):
        """Process with zero cumulative counters returns zeros."""
        io = _make_io_counters(read_bytes=0, write_bytes=0,
                               read_count=0, write_count=0)
        proc = _make_process(io_counters_value=io)

        result = collect_process_io(proc)

        self.assertIsNotNone(result)
        self.assertEqual(result["read_bytes"], 0)
        self.assertEqual(result["write_bytes"], 0)
        self.assertEqual(result["read_count"], 0)
        self.assertEqual(result["write_count"], 0)

    def test_access_denied_on_io_counters(self):
        """AccessDenied when reading io_counters returns None."""
        proc = _make_process(io_counters_raises=psutil.AccessDenied(pid=1))

        result = collect_process_io(proc)
        self.assertIsNone(result)

    def test_no_such_process_on_io_counters(self):
        """NoSuchProcess when reading io_counters returns None."""
        proc = _make_process(io_counters_raises=psutil.NoSuchProcess(pid=1))

        result = collect_process_io(proc)
        self.assertIsNone(result)

    def test_zombie_process_on_io_counters(self):
        """ZombieProcess when reading io_counters returns None."""
        proc = _make_process(io_counters_raises=psutil.ZombieProcess(pid=1))

        result = collect_process_io(proc)
        self.assertIsNone(result)

    def test_access_denied_on_process(self):
        """AccessDenied at the process level returns None."""
        proc = MagicMock()
        proc.oneshot.return_value.__enter__ = MagicMock(
            side_effect=psutil.AccessDenied(pid=1)
        )
        proc.oneshot.return_value.__exit__ = MagicMock(return_value=False)

        result = collect_process_io(proc)
        self.assertIsNone(result)

    def test_no_such_process_at_process_level(self):
        """NoSuchProcess at the process level returns None."""
        proc = MagicMock()
        proc.oneshot.return_value.__enter__ = MagicMock(
            side_effect=psutil.NoSuchProcess(pid=1)
        )
        proc.oneshot.return_value.__exit__ = MagicMock(return_value=False)

        result = collect_process_io(proc)
        self.assertIsNone(result)

    def test_generic_exception_returns_none(self):
        """Unexpected exception returns None (no crash)."""
        proc = MagicMock()
        proc.oneshot.return_value.__enter__ = MagicMock(
            side_effect=RuntimeError("unexpected")
        )
        proc.oneshot.return_value.__exit__ = MagicMock(return_value=False)

        result = collect_process_io(proc)
        self.assertIsNone(result)

    def test_process_with_none_pid_returns_none(self):
        """Process with pid=None returns None."""
        proc = _make_process()
        proc.pid = None

        result = collect_process_io(proc)
        self.assertIsNone(result)


# ===================================================================
# Test: ProcessIOCollector – first observation
# ===================================================================

class TestCollectorFirstObservation(unittest.TestCase):
    def test_first_observation_returns_none(self):
        """First observation for a PID returns None (no rates yet)."""
        collector = ProcessIOCollector()
        proc = _make_process(pid=100, io_counters_value=_make_io_counters(1000, 2000, 5, 10))

        result = collector.collect_single(proc)

        self.assertIsNone(result)

    def test_first_observation_stores_state(self):
        """First observation stores cumulative counters for the next interval."""
        collector = ProcessIOCollector()
        proc = _make_process(pid=100, io_counters_value=_make_io_counters(1000, 2000, 5, 10))

        collector.collect_single(proc)

        self.assertIn(100, collector._prev)
        self.assertEqual(collector._prev[100]["read_bytes"], 1000)
        self.assertEqual(collector._prev[100]["write_bytes"], 2000)


# ===================================================================
# Test: ProcessIOCollector – rate computation
# ===================================================================

class TestCollectorRates(unittest.TestCase):
    @patch("intelligence.io_metrics.time")
    def test_second_observation_returns_rates(self, mock_time):
        """Second observation computes correct rates."""
        mock_time.time.side_effect = [100.0, 101.0]

        collector = ProcessIOCollector()
        proc = _make_process(pid=100, io_counters_value=_make_io_counters(1000, 2000, 5, 10))

        # First observation – stores state, returns None.
        first = collector.collect_single(proc)
        self.assertIsNone(first)

        # Update mock counters for second observation.
        proc.io_counters.return_value = _make_io_counters(2000, 3000, 10, 20)

        second = collector.collect_single(proc)

        self.assertIsNotNone(second)
        self.assertEqual(second["pid"], 100)
        self.assertAlmostEqual(second["read_bytes"], 2000)
        self.assertAlmostEqual(second["write_bytes"], 3000)
        # delta_read=1000, delta_write=1000, elapsed=1.0
        self.assertAlmostEqual(second["read_bytes_per_sec"], 1000.0)
        self.assertAlmostEqual(second["write_bytes_per_sec"], 1000.0)
        self.assertAlmostEqual(second["total_io_bytes_per_sec"], 2000.0)
        self.assertAlmostEqual(second["read_write_ratio"], 1.0)

    @patch("intelligence.io_metrics.time")
    def test_zero_elapsed_time(self, mock_time):
        """Zero elapsed time yields zero rates."""
        mock_time.time.side_effect = [100.0, 100.0]

        collector = ProcessIOCollector()
        proc = _make_process(pid=200, io_counters_value=_make_io_counters(500, 500, 1, 1))

        collector.collect_single(proc)  # first
        proc.io_counters.return_value = _make_io_counters(1500, 1500, 2, 2)
        result = collector.collect_single(proc)  # second, same timestamp

        self.assertIsNotNone(result)
        self.assertEqual(result["read_bytes_per_sec"], 0.0)
        self.assertEqual(result["write_bytes_per_sec"], 0.0)

    @patch("intelligence.io_metrics.time")
    def test_read_write_ratio_read_only(self, mock_time):
        """Only reads, no writes → inf ratio."""
        mock_time.time.side_effect = [100.0, 101.0]

        collector = ProcessIOCollector()
        proc = _make_process(pid=300, io_counters_value=_make_io_counters(0, 0, 0, 0))

        collector.collect_single(proc)  # first
        proc.io_counters.return_value = _make_io_counters(1000, 0, 5, 0)
        result = collector.collect_single(proc)

        self.assertIsNotNone(result)
        self.assertEqual(result["read_write_ratio"], float("inf"))

    @patch("intelligence.io_metrics.time")
    def test_read_write_ratio_write_only(self, mock_time):
        """Only writes, no reads → ratio is 0.0."""
        mock_time.time.side_effect = [100.0, 101.0]

        collector = ProcessIOCollector()
        proc = _make_process(pid=301, io_counters_value=_make_io_counters(0, 0, 0, 0))

        collector.collect_single(proc)  # first
        proc.io_counters.return_value = _make_io_counters(0, 5000, 0, 10)
        result = collector.collect_single(proc)

        self.assertIsNotNone(result)
        self.assertEqual(result["read_write_ratio"], 0.0)

    @patch("intelligence.io_metrics.time")
    def test_read_write_ratio_balanced(self, mock_time):
        """Balanced read/write → ratio close to 1.0."""
        mock_time.time.side_effect = [100.0, 101.0]

        collector = ProcessIOCollector()
        proc = _make_process(pid=302, io_counters_value=_make_io_counters(0, 0, 0, 0))

        collector.collect_single(proc)  # first
        proc.io_counters.return_value = _make_io_counters(2000, 2000, 10, 10)
        result = collector.collect_single(proc)

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["read_write_ratio"], 1.0)

    @patch("intelligence.io_metrics.time")
    def test_rate_calculation_correctness(self, mock_time):
        """Verify exact rate calculation with known values."""
        mock_time.time.side_effect = [0.0, 2.0]

        collector = ProcessIOCollector()
        proc = _make_process(pid=400, io_counters_value=_make_io_counters(10000, 5000, 50, 25))

        collector.collect_single(proc)  # baseline
        proc.io_counters.return_value = _make_io_counters(20000, 10000, 100, 50)
        result = collector.collect_single(proc)

        # delta_read=10000, delta_write=5000, elapsed=2.0
        self.assertAlmostEqual(result["read_bytes_per_sec"], 5000.0)
        self.assertAlmostEqual(result["write_bytes_per_sec"], 2500.0)
        self.assertAlmostEqual(result["total_io_bytes_per_sec"], 7500.0)
        self.assertAlmostEqual(result["read_write_ratio"], 2.0)


# ===================================================================
# Test: ProcessIOCollector – process errors during collect_single
# ===================================================================

class TestCollectorProcessErrors(unittest.TestCase):
    def test_access_denied_on_single_process(self):
        """collect_single returns None when io_counters raises AccessDenied."""
        collector = ProcessIOCollector()
        proc = _make_process(io_counters_raises=psutil.AccessDenied(pid=1))

        result = collector.collect_single(proc)
        self.assertIsNone(result)

    def test_no_such_process_on_single(self):
        """collect_single returns None when process vanishes."""
        collector = ProcessIOCollector()
        proc = _make_process(io_counters_raises=psutil.NoSuchProcess(pid=1))

        result = collector.collect_single(proc)
        self.assertIsNone(result)

    @patch("intelligence.io_metrics.time")
    def test_process_terminates_between_samples(self, mock_time):
        """Process terminates between first and second observation."""
        mock_time.time.side_effect = [100.0, 101.0]

        collector = ProcessIOCollector()
        proc = _make_process(pid=500, io_counters_value=_make_io_counters(100, 200, 1, 2))

        collector.collect_single(proc)  # first – stored

        # Simulate process termination on next call.
        proc.io_counters.side_effect = psutil.NoSuchProcess(pid=500)
        result = collector.collect_single(proc)

        self.assertIsNone(result)

    def test_io_counters_returns_none_fields(self):
        """io_counters returns object with None attributes."""
        io = MagicMock()
        io.read_bytes = None
        io.write_bytes = None
        io.read_count = None
        io.write_count = None
        proc = _make_process(io_counters_value=io)

        result = collect_process_io(proc)

        self.assertIsNotNone(result)
        self.assertEqual(result["read_bytes"], 0)
        self.assertEqual(result["write_bytes"], 0)


# ===================================================================
# Test: ProcessIOCollector – history
# ===================================================================

class TestCollectorHistory(unittest.TestCase):
    @patch("intelligence.io_metrics.time")
    def test_bounded_history(self, mock_time):
        """Per-process history does not exceed history_limit."""
        mock_time.time.side_effect = [float(i) for i in range(10)]

        collector = ProcessIOCollector(history_limit=3)
        proc = _make_process(pid=600, io_counters_value=_make_io_counters(0, 0, 0, 0))

        collector.collect_single(proc)  # 0 – first, no record
        for i in range(1, 8):
            proc.io_counters.return_value = _make_io_counters(
                read_bytes=i * 1000, write_bytes=i * 500,
                read_count=i, write_count=i,
            )
            collector.collect_single(proc)

        history = collector.get_process_history(600)
        self.assertEqual(len(history), 3)

    @patch("intelligence.io_metrics.time")
    def test_get_process_history_empty(self, mock_time):
        """History for unknown PID returns empty list."""
        collector = ProcessIOCollector()
        self.assertEqual(collector.get_process_history(999), [])

    @patch("intelligence.io_metrics.time")
    def test_clear_resets_state(self, mock_time):
        """clear() removes all stored state."""
        mock_time.time.side_effect = [100.0, 101.0]

        collector = ProcessIOCollector()
        proc = _make_process(pid=700, io_counters_value=_make_io_counters(100, 200, 1, 2))

        collector.collect_single(proc)  # first
        proc.io_counters.return_value = _make_io_counters(200, 400, 2, 4)
        collector.collect_single(proc)  # second

        collector.clear()

        self.assertEqual(len(collector._prev), 0)
        self.assertEqual(len(collector._prev_timestamp), 0)
        self.assertEqual(len(collector._history), 0)


# ===================================================================
# Test: ProcessIOCollector – metrics dict structure
# ===================================================================

class TestCollectorMetricsStructure(unittest.TestCase):
    @patch("intelligence.io_metrics.time")
    def test_metrics_dict_has_all_keys(self, mock_time):
        """Metrics dict contains all expected keys."""
        mock_time.time.side_effect = [100.0, 101.0]

        collector = ProcessIOCollector()
        proc = _make_process(
            pid=800, name="mydb", status="sleeping",
            io_counters_value=_make_io_counters(500, 300, 5, 3),
        )

        collector.collect_single(proc)
        proc.io_counters.return_value = _make_io_counters(1500, 800, 15, 8)
        result = collector.collect_single(proc)

        expected_keys = {
            "pid", "name", "state",
            "cpu_percent", "memory_percent",
            "read_bytes", "write_bytes", "read_count", "write_count",
            "read_bytes_per_sec", "write_bytes_per_sec",
            "total_io_bytes_per_sec", "read_write_ratio",
            "timestamp",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    @patch("intelligence.io_metrics.time")
    def test_rates_are_rounded(self, mock_time):
        """Rate values are rounded to 2 decimal places."""
        mock_time.time.side_effect = [100.0, 101.0]

        collector = ProcessIOCollector()
        proc = _make_process(pid=801, io_counters_value=_make_io_counters(0, 0, 0, 0))

        collector.collect_single(proc)
        proc.io_counters.return_value = _make_io_counters(100, 100, 1, 1)
        result = collector.collect_single(proc)

        self.assertAlmostEqual(result["read_bytes_per_sec"], 100.0, places=2)
        self.assertAlmostEqual(result["write_bytes_per_sec"], 100.0, places=2)


# ===================================================================
# Test: ProcessIOCollector – collect_all
# ===================================================================

class TestCollectorCollectAll(unittest.TestCase):
    @patch("intelligence.io_metrics.psutil")
    @patch("intelligence.io_metrics.time")
    def test_collect_all_skips_inaccessible(self, mock_time, mock_psutil):
        """collect_all skips processes with AccessDenied on io_counters."""
        # Wire real exception classes so except clauses work in io_metrics.py
        mock_psutil.AccessDenied = psutil.AccessDenied
        mock_psutil.NoSuchProcess = psutil.NoSuchProcess
        mock_psutil.ZombieProcess = psutil.ZombieProcess

        mock_time.time.side_effect = [100.0, 101.0]

        good_proc = _make_process(pid=1, name="good", io_counters_value=_make_io_counters(100, 200, 1, 2))
        bad_proc = _make_process(pid=2, name="bad", io_counters_raises=psutil.AccessDenied(pid=2))

        mock_psutil.process_iter.return_value = [good_proc, bad_proc]

        collector = ProcessIOCollector()

        # First pass – no rates (baseline).
        results_first = collector.collect_all()
        self.assertEqual(len(results_first), 0)

        # Second pass – rates computed for good_proc only.
        good_proc.io_counters.return_value = _make_io_counters(200, 400, 2, 4)
        bad_proc.io_counters.side_effect = psutil.AccessDenied(pid=2)
        results_second = collector.collect_all()

        self.assertEqual(len(results_second), 1)
        self.assertEqual(results_second[0]["pid"], 1)

    @patch("intelligence.io_metrics.psutil")
    @patch("intelligence.io_metrics.time")
    def test_collect_all_returns_empty_first_time(self, mock_time, mock_psutil):
        """First call to collect_all returns empty list (baseline)."""
        mock_psutil.AccessDenied = psutil.AccessDenied
        mock_psutil.NoSuchProcess = psutil.NoSuchProcess
        mock_psutil.ZombieProcess = psutil.ZombieProcess

        mock_time.time.return_value = 100.0

        proc = _make_process(pid=10, io_counters_value=_make_io_counters(500, 500, 5, 5))
        mock_psutil.process_iter.return_value = [proc]

        collector = ProcessIOCollector()
        results = collector.collect_all()

        self.assertEqual(results, [])

    @patch("intelligence.io_metrics.psutil")
    @patch("intelligence.io_metrics.time")
    def test_collect_all_sorted_by_total_io(self, mock_time, mock_psutil):
        """Results are sorted by total_io_bytes_per_sec descending."""
        mock_psutil.AccessDenied = psutil.AccessDenied
        mock_psutil.NoSuchProcess = psutil.NoSuchProcess
        mock_psutil.ZombieProcess = psutil.ZombieProcess

        mock_time.time.side_effect = [100.0, 100.0, 101.0, 101.0]

        proc_a = _make_process(pid=1, name="low_io",
                               io_counters_value=_make_io_counters(0, 0, 0, 0))
        proc_b = _make_process(pid=2, name="high_io",
                               io_counters_value=_make_io_counters(0, 0, 0, 0))
        mock_psutil.process_iter.return_value = [proc_a, proc_b]

        collector = ProcessIOCollector()
        collector.collect_all()  # baseline

        # Second pass: proc_b has much more I/O.
        proc_a.io_counters.return_value = _make_io_counters(100, 100, 1, 1)
        proc_b.io_counters.return_value = _make_io_counters(10000, 5000, 100, 50)
        results = collector.collect_all()

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["name"], "high_io")
        self.assertEqual(results[1]["name"], "low_io")


if __name__ == "__main__":
    unittest.main()
