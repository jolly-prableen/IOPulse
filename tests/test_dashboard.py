"""
tests/test_dashboard.py – Unit Tests for Dashboard Input Helpers & Dispatch
OS Sentinel – Teammate B (Phase 5)

These tests verify:
  - Input parsing/validation helpers (page string, request queue, ints).
  - Algorithm dispatch returns correct structured keys.
  - Invalid inputs produce proper error messages (not crashes).
  - No algorithm logic is duplicated in the dashboard module.

These tests do NOT instantiate Tkinter or depend on GUI pixel positions.
"""

import ast
import inspect
import textwrap
import unittest

from dashboard.memory_io_dashboard import (
    parse_page_string,
    parse_request_queue,
    parse_positive_int,
    parse_non_negative_int,
)

# Import the actual algorithm modules to verify the dashboard delegates
from memory.page_replacement import fifo, lru, optimal, compare_algorithms
from disk_io.fcfs import fcfs
from disk_io.sstf import sstf
from disk_io.scan import scan
from disk_io.cscan import cscan


# ===================================================================
# Test: parse_page_string
# ===================================================================

class TestParsePageString(unittest.TestCase):
    """Test the page reference string parser."""

    def test_space_separated(self):
        self.assertEqual(parse_page_string("1 2 3 4"), [1, 2, 3, 4])

    def test_comma_separated(self):
        self.assertEqual(parse_page_string("1,2,3,4"), [1, 2, 3, 4])

    def test_mixed_delimiters(self):
        self.assertEqual(parse_page_string("1, 2 3,4"), [1, 2, 3, 4])

    def test_extra_whitespace(self):
        self.assertEqual(parse_page_string("  1  2  3  "), [1, 2, 3])

    def test_negative_pages_allowed(self):
        # Page numbers can be any int (algorithm-specific meaning).
        self.assertEqual(parse_page_string("-1 2 -3"), [-1, 2, -3])

    def test_empty_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_page_string("")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_whitespace_only_raises(self):
        with self.assertRaises(ValueError):
            parse_page_string("   ")

    def test_non_integer_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_page_string("1 2 abc 4")
        self.assertIn("abc", str(ctx.exception))

    def test_float_raises(self):
        with self.assertRaises(ValueError):
            parse_page_string("1.5 2 3")


# ===================================================================
# Test: parse_request_queue
# ===================================================================

class TestParseRequestQueue(unittest.TestCase):
    """Test the disk request queue parser."""

    def test_valid_queue(self):
        self.assertEqual(
            parse_request_queue("98 183 37 122 14 124 65 67"),
            [98, 183, 37, 122, 14, 124, 65, 67],
        )

    def test_comma_separated(self):
        self.assertEqual(parse_request_queue("10,20,30"), [10, 20, 30])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            parse_request_queue("")

    def test_negative_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_request_queue("10 -5 20")
        self.assertIn("negative", str(ctx.exception).lower())

    def test_non_integer_raises(self):
        with self.assertRaises(ValueError):
            parse_request_queue("10 abc 20")


# ===================================================================
# Test: parse_positive_int / parse_non_negative_int
# ===================================================================

class TestParseInt(unittest.TestCase):
    """Test the integer parsing helpers."""

    def test_positive_valid(self):
        self.assertEqual(parse_positive_int("3", "Frames"), 3)

    def test_positive_zero_raises(self):
        with self.assertRaises(ValueError):
            parse_positive_int("0", "Frames")

    def test_positive_negative_raises(self):
        with self.assertRaises(ValueError):
            parse_positive_int("-1", "Frames")

    def test_positive_empty_raises(self):
        with self.assertRaises(ValueError):
            parse_positive_int("", "Frames")

    def test_positive_non_int_raises(self):
        with self.assertRaises(ValueError):
            parse_positive_int("abc", "Frames")

    def test_non_negative_zero(self):
        self.assertEqual(parse_non_negative_int("0", "Head"), 0)

    def test_non_negative_valid(self):
        self.assertEqual(parse_non_negative_int("53", "Head"), 53)

    def test_non_negative_negative_raises(self):
        with self.assertRaises(ValueError):
            parse_non_negative_int("-1", "Head")


# ===================================================================
# Test: Algorithm dispatch returns correct structure
# ===================================================================

class TestAlgorithmDispatch(unittest.TestCase):
    """Verify that the existing algorithm modules return the expected keys.

    This confirms the dashboard can safely access these keys without
    duplicating any algorithm logic.
    """

    def test_fifo_returns_expected_keys(self):
        result = fifo([1, 2, 3, 1, 4], 3)
        self.assertIn("algorithm", result)
        self.assertIn("page_faults", result)
        self.assertIn("page_hits", result)
        self.assertIn("fault_rate", result)
        self.assertIn("hit_rate", result)
        self.assertIn("steps", result)
        self.assertEqual(result["algorithm"], "FIFO")

    def test_lru_returns_expected_keys(self):
        result = lru([1, 2, 3, 1, 4], 3)
        self.assertIn("algorithm", result)
        self.assertEqual(result["algorithm"], "LRU")

    def test_optimal_returns_expected_keys(self):
        result = optimal([1, 2, 3, 1, 4], 3)
        self.assertIn("algorithm", result)
        self.assertEqual(result["algorithm"], "Optimal")

    def test_compare_returns_all_three(self):
        result = compare_algorithms([1, 2, 3], 2)
        self.assertIn("FIFO", result)
        self.assertIn("LRU", result)
        self.assertIn("Optimal", result)

    def test_fcfs_returns_expected_keys(self):
        result = fcfs([98, 183, 37], 53, 200)
        self.assertIn("algorithm", result)
        self.assertIn("total_head_movement", result)
        self.assertIn("average_seek_distance", result)
        self.assertIn("steps", result)
        self.assertEqual(result["algorithm"], "FCFS")

    def test_sstf_returns_expected_keys(self):
        result = sstf([98, 183, 37], 53, 200)
        self.assertEqual(result["algorithm"], "SSTF")

    def test_scan_returns_expected_keys(self):
        result = scan([98, 183, 37], 53, 200, "right")
        self.assertIn("direction", result)
        self.assertEqual(result["algorithm"], "SCAN")

    def test_cscan_returns_expected_keys(self):
        result = cscan([98, 183, 37], 53, 200, "right")
        self.assertIn("direction", result)
        self.assertEqual(result["algorithm"], "C-SCAN")

    def test_step_dict_structure(self):
        """Each step should have from, to, distance keys."""
        result = fcfs([10, 20], 0, 100)
        for step in result["steps"]:
            self.assertIn("from", step)
            self.assertIn("to", step)
            self.assertIn("distance", step)

    def test_page_step_structure(self):
        """Each page step should have page, frames, hit, fault keys."""
        result = fifo([1, 2, 1], 2)
        for step in result["steps"]:
            self.assertIn("page", step)
            self.assertIn("frames", step)
            self.assertIn("hit", step)
            self.assertIn("fault", step)


# ===================================================================
# Test: Dashboard does NOT duplicate algorithm logic
# ===================================================================

class TestNoDuplicateLogic(unittest.TestCase):
    """Verify the dashboard module does not re-implement algorithms.

    We inspect the source code of the dashboard module to ensure it
    does NOT contain page replacement or disk scheduling logic.
    """

    @classmethod
    def setUpClass(cls):
        """Read the dashboard source code once."""
        import dashboard.memory_io_dashboard as mod
        cls.source = inspect.getsource(mod)

    def test_no_page_replacement_logic(self):
        """Dashboard should not implement page replacement loops."""
        # These are implementation patterns from the algorithms, not
        # something the dashboard would use for display purposes.
        forbidden = [
            "next_replace = (next_replace + 1) % num_frames",
            "victim = last_used.index(min(last_used))",
            "_find_optimal_victim",
        ]
        for pattern in forbidden:
            self.assertNotIn(
                pattern, self.source,
                f"Dashboard contains algorithm logic: '{pattern}'"
            )

    def test_no_disk_scheduling_logic(self):
        """Dashboard should not implement disk scheduling loops."""
        forbidden = [
            "closest = min(pending",
            "pending.remove(",
        ]
        for pattern in forbidden:
            self.assertNotIn(
                pattern, self.source,
                f"Dashboard contains algorithm logic: '{pattern}'"
            )

    def test_imports_existing_modules(self):
        """Dashboard should import from the existing module packages."""
        self.assertIn("from memory.page_replacement import", self.source)
        self.assertIn("from disk_io.fcfs import", self.source)
        self.assertIn("from memory.monitor import", self.source)
        self.assertIn("from intelligence.memory_anomaly import", self.source)


if __name__ == "__main__":
    unittest.main()
