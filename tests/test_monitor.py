"""
tests/test_monitor.py – Unit tests for memory/monitor.py
IOPulse

These tests verify that the monitoring functions return correctly structured
data.  They run against the REAL system, so exact values cannot be predicted,
but we can assert types, required keys, and reasonable value ranges.
"""

import unittest
from memory.monitor import (
    bytes_to_mb,
    get_system_memory,
    get_process_memory,
    get_memory_snapshot,
)


class TestBytesToMb(unittest.TestCase):
    """Test the helper that converts bytes → megabytes."""

    def test_zero(self):
        self.assertEqual(bytes_to_mb(0), 0.0)

    def test_one_mb(self):
        # 1 MB = 1,048,576 bytes
        self.assertEqual(bytes_to_mb(1048576), 1.0)

    def test_fractional(self):
        # 1,500,000 bytes ≈ 1.43 MB
        result = bytes_to_mb(1500000)
        self.assertAlmostEqual(result, 1.43, places=2)


class TestGetSystemMemory(unittest.TestCase):
    """Test system-wide memory snapshot."""

    def setUp(self):
        self.data = get_system_memory()

    def test_returns_dict(self):
        self.assertIsInstance(self.data, dict)

    def test_required_keys_present(self):
        expected_keys = [
            "total_ram_mb", "used_ram_mb", "available_ram_mb",
            "ram_percent", "total_swap_mb", "used_swap_mb",
            "swap_percent", "timestamp",
        ]
        for key in expected_keys:
            self.assertIn(key, self.data, f"Missing key: {key}")

    def test_ram_values_are_positive(self):
        self.assertGreater(self.data["total_ram_mb"], 0)
        self.assertGreaterEqual(self.data["used_ram_mb"], 0)
        self.assertGreaterEqual(self.data["available_ram_mb"], 0)

    def test_ram_percent_in_range(self):
        self.assertGreaterEqual(self.data["ram_percent"], 0)
        self.assertLessEqual(self.data["ram_percent"], 100)

    def test_swap_percent_in_range(self):
        # Swap might be disabled (0 total), but percent should still be valid.
        # NOTE: On Windows, the page file can dynamically grow beyond its
        # initial configured size, so psutil may report >100%.  We use a
        # relaxed upper bound of 200% to accommodate this.
        self.assertGreaterEqual(self.data["swap_percent"], 0)
        self.assertLessEqual(self.data["swap_percent"], 200)

    def test_timestamp_is_numeric(self):
        self.assertIsInstance(self.data["timestamp"], float)


class TestGetProcessMemory(unittest.TestCase):
    """Test per-process memory collection."""

    def test_returns_list(self):
        result = get_process_memory(top_n=5)
        self.assertIsInstance(result, list)

    def test_respects_top_n(self):
        result = get_process_memory(top_n=3)
        self.assertLessEqual(len(result), 3)

    def test_process_dict_keys(self):
        result = get_process_memory(top_n=1)
        if result:  # At least one process should exist
            proc = result[0]
            self.assertIn("pid", proc)
            self.assertIn("name", proc)
            self.assertIn("memory_percent", proc)
            self.assertIn("memory_rss_mb", proc)

    def test_sorted_descending(self):
        result = get_process_memory(top_n=10)
        percents = [p["memory_percent"] for p in result]
        self.assertEqual(percents, sorted(percents, reverse=True))


class TestGetMemorySnapshot(unittest.TestCase):
    """Test the combined snapshot function."""

    def test_has_system_and_processes(self):
        snap = get_memory_snapshot(top_n=5)
        self.assertIn("system", snap)
        self.assertIn("processes", snap)
        self.assertIsInstance(snap["system"], dict)
        self.assertIsInstance(snap["processes"], list)


if __name__ == "__main__":
    unittest.main()
