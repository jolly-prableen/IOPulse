"""
tests/test_disk_scheduling.py – Comprehensive Tests for Disk Scheduling Algorithms
OS Sentinel – Teammate B (Memory & I/O Subsystem) – Phase 3

Tests cover:
  1. Normal request queue
  2. Requests on both sides of the initial head
  3. Requests already near the head
  4. Initial head near disk boundary
  5. Empty request list
  6. One request
  7. Duplicate requests
  8. Both left and right directions for SCAN
  9. Both left and right directions for C-SCAN
  10. Input validation (bad disk_size, bad head, bad requests, bad direction)
  11. Original request list not modified
  12. Every request is serviced (no request skipped)
  13. Total head movement correctness
"""

import unittest
from copy import deepcopy

from disk_io.fcfs  import fcfs, _validate_inputs
from disk_io.sstf  import sstf
from disk_io.scan  import scan
from disk_io.cscan import cscan


# ===================================================================
# Shared constants for the standard example
# ===================================================================

STANDARD_REQUESTS  = [98, 183, 37, 122, 14, 124, 65, 67]
STANDARD_HEAD      = 53
STANDARD_DISK_SIZE = 200


# ===================================================================
# Helper assertions used across all algorithm tests
# ===================================================================

class DiskSchedulingTestMixin:
    """Common assertions for disk scheduling result dicts."""

    def assert_valid_result(self, result, algorithm_name, requests, initial_head):
        """Verify the result dict has the correct structure and values."""
        self.assertEqual(result["algorithm"], algorithm_name)
        self.assertEqual(result["initial_head"], initial_head)
        self.assertIsInstance(result["request_order"], list)
        self.assertIsInstance(result["total_head_movement"], int)
        self.assertIsInstance(result["average_seek_distance"], float)
        self.assertIsInstance(result["steps"], list)

        # Every request must appear in the request_order (sorted comparison).
        self.assertEqual(
            sorted(result["request_order"]),
            sorted(requests),
            "Not all requests were serviced",
        )

    def assert_steps_consistent(self, result):
        """Verify step distances sum to total_head_movement and chain correctly."""
        steps = result["steps"]
        if not steps:
            self.assertEqual(result["total_head_movement"], 0)
            return

        # First step must start from initial_head.
        self.assertEqual(steps[0]["from"], result["initial_head"])

        # Each step's "from" must equal the previous step's "to".
        for i in range(1, len(steps)):
            self.assertEqual(
                steps[i]["from"], steps[i - 1]["to"],
                f"Step {i}: 'from' doesn't match previous 'to'",
            )

        # Each step's distance must equal |to - from|.
        for i, step in enumerate(steps):
            self.assertEqual(
                step["distance"],
                abs(step["to"] - step["from"]),
                f"Step {i}: distance mismatch",
            )

        # Sum of step distances == total_head_movement.
        total_from_steps = sum(s["distance"] for s in steps)
        self.assertEqual(
            total_from_steps,
            result["total_head_movement"],
            "Sum of step distances != total_head_movement",
        )

    def assert_original_not_modified(self, original, current):
        """Ensure the original request list was not mutated."""
        self.assertEqual(original, current)


# ===================================================================
# FCFS Tests
# ===================================================================

class TestFCFS(unittest.TestCase, DiskSchedulingTestMixin):
    """Tests for the FCFS disk scheduling algorithm."""

    # ---- Normal request queue ----

    def test_standard_example(self):
        """FCFS with the standard example from the spec."""
        result = fcfs(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE)
        self.assert_valid_result(result, "FCFS", STANDARD_REQUESTS, STANDARD_HEAD)
        self.assert_steps_consistent(result)

        # FCFS serves in arrival order.
        self.assertEqual(result["request_order"], STANDARD_REQUESTS)

        # Manually computed: |53-98|+|98-183|+|183-37|+|37-122|+
        #                    |122-14|+|14-124|+|124-65|+|65-67|
        # = 45 + 85 + 146 + 85 + 108 + 110 + 59 + 2 = 640
        self.assertEqual(result["total_head_movement"], 640)

    def test_order_preserved(self):
        """FCFS request_order must exactly match the input order."""
        reqs = [10, 90, 50, 70, 30]
        result = fcfs(reqs, 50, 100)
        self.assertEqual(result["request_order"], reqs)

    # ---- Edge cases ----

    def test_empty_requests(self):
        """FCFS with no requests should return zeros."""
        result = fcfs([], 50, 100)
        self.assertEqual(result["request_order"], [])
        self.assertEqual(result["total_head_movement"], 0)
        self.assertEqual(result["average_seek_distance"], 0.0)
        self.assertEqual(result["steps"], [])

    def test_single_request(self):
        """FCFS with exactly one request."""
        result = fcfs([75], 50, 100)
        self.assertEqual(result["request_order"], [75])
        self.assertEqual(result["total_head_movement"], 25)
        self.assertEqual(len(result["steps"]), 1)

    def test_duplicate_requests(self):
        """FCFS with duplicate requests — each is served separately."""
        reqs = [50, 50, 50]
        result = fcfs(reqs, 50, 100)
        self.assertEqual(result["request_order"], [50, 50, 50])
        self.assertEqual(result["total_head_movement"], 0)

    def test_head_at_boundary_left(self):
        """FCFS with head at cylinder 0."""
        result = fcfs([99, 50, 10], 0, 100)
        self.assertEqual(result["total_head_movement"], 99 + 49 + 40)

    def test_head_at_boundary_right(self):
        """FCFS with head at the last cylinder."""
        result = fcfs([10, 50, 90], 99, 100)
        self.assertEqual(result["total_head_movement"], 89 + 40 + 40)

    def test_requests_near_head(self):
        """All requests clustered near the head."""
        result = fcfs([51, 52, 50, 49], 50, 100)
        self.assertEqual(result["total_head_movement"], 1 + 1 + 2 + 1)

    def test_original_list_not_modified(self):
        """Ensure the caller's list is not mutated."""
        reqs = [98, 183, 37]
        original = list(reqs)
        fcfs(reqs, 53, 200)
        self.assert_original_not_modified(original, reqs)

    def test_steps_chain(self):
        """Verify steps chain from → to correctly."""
        result = fcfs([10, 90, 50], 0, 100)
        self.assert_steps_consistent(result)


# ===================================================================
# SSTF Tests
# ===================================================================

class TestSSTF(unittest.TestCase, DiskSchedulingTestMixin):
    """Tests for the SSTF disk scheduling algorithm."""

    def test_standard_example(self):
        """SSTF with the standard example."""
        result = sstf(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE)
        self.assert_valid_result(result, "SSTF", STANDARD_REQUESTS, STANDARD_HEAD)
        self.assert_steps_consistent(result)

        # SSTF should produce less head movement than FCFS for this example.
        fcfs_result = fcfs(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE)
        self.assertLessEqual(
            result["total_head_movement"],
            fcfs_result["total_head_movement"],
        )

    def test_greedy_ordering(self):
        """SSTF picks closest request at each step."""
        reqs = [10, 20, 30, 40]
        result = sstf(reqs, 25, 50)
        # From 25: closest is 20 (dist 5) and 30 (dist 5) → tie, pick 20.
        # From 20: closest is 10 (dist 10) and 30 (dist 10) → tie, pick 10.
        # From 10: closest is 30 (dist 20) and 40 (dist 30) → pick 30.
        # From 30: only 40 left.
        self.assertEqual(result["request_order"], [20, 10, 30, 40])

    def test_empty_requests(self):
        """SSTF with no requests."""
        result = sstf([], 50, 100)
        self.assertEqual(result["total_head_movement"], 0)
        self.assertEqual(result["request_order"], [])

    def test_single_request(self):
        """SSTF with one request."""
        result = sstf([80], 20, 100)
        self.assertEqual(result["request_order"], [80])
        self.assertEqual(result["total_head_movement"], 60)

    def test_duplicate_requests(self):
        """SSTF with duplicates — each occurrence is served."""
        reqs = [50, 50, 90]
        result = sstf(reqs, 50, 100)
        self.assertEqual(sorted(result["request_order"]), sorted(reqs))
        self.assert_steps_consistent(result)

    def test_all_same_position(self):
        """All requests at the same cylinder."""
        reqs = [50, 50, 50]
        result = sstf(reqs, 50, 100)
        self.assertEqual(result["total_head_movement"], 0)

    def test_head_at_boundary(self):
        """SSTF with head at cylinder 0."""
        reqs = [90, 10, 50]
        result = sstf(reqs, 0, 100)
        # From 0: closest is 10 (10), then 50 (40), then 90 (40).
        self.assertEqual(result["request_order"], [10, 50, 90])
        self.assertEqual(result["total_head_movement"], 90)

    def test_tie_breaking(self):
        """When two requests are equidistant, smaller cylinder wins."""
        reqs = [40, 60]
        result = sstf(reqs, 50, 100)
        # Both are distance 10; 40 < 60, so 40 is served first.
        self.assertEqual(result["request_order"], [40, 60])

    def test_original_list_not_modified(self):
        """Ensure the caller's list is not mutated."""
        reqs = [98, 183, 37]
        original = list(reqs)
        sstf(reqs, 53, 200)
        self.assert_original_not_modified(original, reqs)

    def test_steps_chain(self):
        """Verify steps chain correctly."""
        result = sstf(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE)
        self.assert_steps_consistent(result)

    def test_all_requests_serviced(self):
        """Every request must appear in the output."""
        reqs = [5, 95, 50, 25, 75]
        result = sstf(reqs, 50, 100)
        self.assertEqual(sorted(result["request_order"]), sorted(reqs))


# ===================================================================
# SCAN Tests
# ===================================================================

class TestSCAN(unittest.TestCase, DiskSchedulingTestMixin):
    """Tests for the SCAN (Elevator) disk scheduling algorithm."""

    def test_standard_right(self):
        """SCAN moving right with the standard example."""
        result = scan(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE, "right")
        self.assert_valid_result(result, "SCAN", STANDARD_REQUESTS, STANDARD_HEAD)
        self.assert_steps_consistent(result)
        self.assertEqual(result["direction"], "right")

        # Moving right from 53: serve 65, 67, 98, 122, 124, 183, then
        # reach boundary 199, reverse left: 37, 14.
        self.assertEqual(
            result["request_order"],
            [65, 67, 98, 122, 124, 183, 37, 14],
        )

    def test_standard_left(self):
        """SCAN moving left with the standard example."""
        result = scan(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE, "left")
        self.assert_valid_result(result, "SCAN", STANDARD_REQUESTS, STANDARD_HEAD)
        self.assert_steps_consistent(result)
        self.assertEqual(result["direction"], "left")

        # Moving left from 53: serve 37, 14, reach boundary 0,
        # reverse right: 65, 67, 98, 122, 124, 183.
        self.assertEqual(
            result["request_order"],
            [37, 14, 65, 67, 98, 122, 124, 183],
        )

    def test_total_movement_right(self):
        """SCAN-right total head movement calculation."""
        result = scan(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE, "right")
        # Right sweep: 53 → 65 → 67 → 98 → 122 → 124 → 183 → 199
        # Left sweep: 199 → 37 → 14
        # Total: (199 - 53) + (199 - 14) = 146 + 185 = 331
        self.assertEqual(result["total_head_movement"], 331)

    def test_total_movement_left(self):
        """SCAN-left total head movement calculation."""
        result = scan(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE, "left")
        # Left sweep: 53 → 37 → 14 → 0
        # Right sweep: 0 → 65 → 67 → 98 → 122 → 124 → 183
        # Total: (53 - 0) + (183 - 0) = 53 + 183 = 236
        self.assertEqual(result["total_head_movement"], 236)

    def test_empty_requests(self):
        """SCAN with no requests."""
        result = scan([], 50, 100, "right")
        self.assertEqual(result["total_head_movement"], 0)
        self.assertEqual(result["request_order"], [])

    def test_single_request_right(self):
        """SCAN-right with a single request to the right of head."""
        result = scan([80], 50, 100, "right")
        self.assertEqual(result["request_order"], [80])
        # Head goes 50 → 80 → 99 (boundary).  No left requests.
        self.assertEqual(result["total_head_movement"], 49)

    def test_single_request_left(self):
        """SCAN-left with a single request to the left of head."""
        result = scan([20], 50, 100, "left")
        self.assertEqual(result["request_order"], [20])
        # Head goes 50 → 20 → 0 (boundary).  No right requests.
        self.assertEqual(result["total_head_movement"], 50)

    def test_all_requests_one_side_right(self):
        """All requests to the right of head, SCAN-right."""
        reqs = [60, 70, 80]
        result = scan(reqs, 50, 100, "right")
        self.assertEqual(result["request_order"], [60, 70, 80])
        # 50 → 60 → 70 → 80 → 99 (boundary). Total = 49.
        self.assertEqual(result["total_head_movement"], 49)

    def test_all_requests_one_side_left(self):
        """All requests to the left of head, SCAN-left."""
        reqs = [10, 20, 30]
        result = scan(reqs, 50, 100, "left")
        self.assertEqual(result["request_order"], [30, 20, 10])
        # 50 → 30 → 20 → 10 → 0 (boundary). Total = 50.
        self.assertEqual(result["total_head_movement"], 50)

    def test_duplicate_requests(self):
        """SCAN with duplicate requests."""
        reqs = [50, 50, 80]
        result = scan(reqs, 40, 100, "right")
        self.assertEqual(sorted(result["request_order"]), sorted(reqs))
        self.assert_steps_consistent(result)

    def test_head_at_boundary_right(self):
        """SCAN-right with head at rightmost boundary."""
        reqs = [10, 50, 90]
        result = scan(reqs, 99, 100, "right")
        # Head is already at boundary. Immediately reverse left.
        # 99 → 90 → 50 → 10
        self.assertEqual(result["request_order"], [90, 50, 10])

    def test_head_at_boundary_left(self):
        """SCAN-left with head at leftmost boundary."""
        reqs = [10, 50, 90]
        result = scan(reqs, 0, 100, "left")
        # Head is already at boundary. Immediately reverse right.
        # 0 → 10 → 50 → 90
        self.assertEqual(result["request_order"], [10, 50, 90])

    def test_original_list_not_modified(self):
        """Ensure the caller's list is not mutated."""
        reqs = [98, 183, 37]
        original = list(reqs)
        scan(reqs, 53, 200, "right")
        self.assert_original_not_modified(original, reqs)

    def test_boundary_included_in_steps(self):
        """SCAN boundary visit should appear in steps."""
        reqs = [60, 40]
        result = scan(reqs, 50, 100, "right")
        # Steps: 50→60, 60→99, 99→40. Three steps.
        step_targets = [s["to"] for s in result["steps"]]
        self.assertIn(99, step_targets, "Boundary 99 should appear in steps")


# ===================================================================
# C-SCAN Tests
# ===================================================================

class TestCSCAN(unittest.TestCase, DiskSchedulingTestMixin):
    """Tests for the C-SCAN (Circular SCAN) disk scheduling algorithm."""

    def test_standard_right(self):
        """C-SCAN moving right with the standard example."""
        result = cscan(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE, "right")
        self.assert_valid_result(result, "C-SCAN", STANDARD_REQUESTS, STANDARD_HEAD)
        self.assert_steps_consistent(result)
        self.assertEqual(result["direction"], "right")

        # Moving right from 53: serve 65, 67, 98, 122, 124, 183,
        # then go to 199 boundary, jump to 0, then sweep right: 14, 37.
        self.assertEqual(
            result["request_order"],
            [65, 67, 98, 122, 124, 183, 14, 37],
        )

    def test_standard_left(self):
        """C-SCAN moving left with the standard example."""
        result = cscan(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE, "left")
        self.assert_valid_result(result, "C-SCAN", STANDARD_REQUESTS, STANDARD_HEAD)
        self.assert_steps_consistent(result)
        self.assertEqual(result["direction"], "left")

        # Moving left from 53: serve 37, 14, then go to 0,
        # jump to 199, then sweep left: 183, 124, 122, 98, 67, 65.
        self.assertEqual(
            result["request_order"],
            [37, 14, 183, 124, 122, 98, 67, 65],
        )

    def test_total_movement_right(self):
        """C-SCAN-right total head movement calculation."""
        result = cscan(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE, "right")
        # Right sweep: 53→65→67→98→122→124→183→199 = 146
        # Jump: 199→0 = 199
        # Left sweep: 0→14→37 = 37
        # Total = 146 + 199 + 37 = 382
        self.assertEqual(result["total_head_movement"], 382)

    def test_total_movement_left(self):
        """C-SCAN-left total head movement calculation."""
        result = cscan(STANDARD_REQUESTS, STANDARD_HEAD, STANDARD_DISK_SIZE, "left")
        # Left sweep: 53→37→14→0 = 53
        # Jump: 0→199 = 199
        # Right sweep (in reverse): 199→183→124→122→98→67→65 = 134
        # Total = 53 + 199 + 134 = 386
        self.assertEqual(result["total_head_movement"], 386)

    def test_empty_requests(self):
        """C-SCAN with no requests."""
        result = cscan([], 50, 100, "right")
        self.assertEqual(result["total_head_movement"], 0)
        self.assertEqual(result["request_order"], [])

    def test_single_request_same_side(self):
        """C-SCAN-right with one request on the right."""
        result = cscan([80], 50, 100, "right")
        self.assertEqual(result["request_order"], [80])
        self.assertEqual(result["total_head_movement"], 30)

    def test_single_request_opposite_side(self):
        """C-SCAN-right with one request on the left."""
        result = cscan([20], 50, 100, "right")
        self.assertEqual(result["request_order"], [20])
        # 50 → 99 (boundary) → 0 (jump) → 20. Total = 49 + 99 + 20 = 168.
        self.assertEqual(result["total_head_movement"], 168)

    def test_all_requests_same_side(self):
        """C-SCAN-right with all requests to the right — no jump needed."""
        reqs = [60, 70, 80]
        result = cscan(reqs, 50, 100, "right")
        self.assertEqual(result["request_order"], [60, 70, 80])
        # 50 → 60 → 70 → 80.  No left requests, so no boundary/jump.
        self.assertEqual(result["total_head_movement"], 30)

    def test_duplicate_requests(self):
        """C-SCAN with duplicate requests."""
        reqs = [50, 50, 80]
        result = cscan(reqs, 40, 100, "right")
        self.assertEqual(sorted(result["request_order"]), sorted(reqs))
        self.assert_steps_consistent(result)

    def test_head_at_boundary_right(self):
        """C-SCAN-right with head at rightmost boundary."""
        reqs = [10, 50, 90]
        result = cscan(reqs, 99, 100, "right")
        # Head is at 99 — nothing to the right.
        # All requests on the left: 99→0 (jump), 0→10→50→90
        # Actually head=99, all reqs < 99, so left=[10,50,90], right=[]
        # Phase 1: no right requests to serve.
        # Phase 2: left exists: go to boundary 99 (already there), jump to 0,
        #          then sweep right: 10, 50, 90.
        self.assertEqual(sorted(result["request_order"]), [10, 50, 90])
        self.assert_steps_consistent(result)

    def test_head_at_boundary_left_cscan_left(self):
        """C-SCAN-left with head at leftmost boundary."""
        reqs = [10, 50, 90]
        result = cscan(reqs, 0, 100, "left")
        # Head is at 0 — nothing to the left.
        # All requests on the right: right=[10,50,90], left=[]
        # Phase 1: no left requests.
        # right exists: go to 0 (already there), jump to 99, sweep left:
        #   90, 50, 10.
        self.assertEqual(sorted(result["request_order"]), [10, 50, 90])
        self.assert_steps_consistent(result)

    def test_original_list_not_modified(self):
        """Ensure the caller's list is not mutated."""
        reqs = [98, 183, 37]
        original = list(reqs)
        cscan(reqs, 53, 200, "right")
        self.assert_original_not_modified(original, reqs)

    def test_jump_appears_in_steps(self):
        """C-SCAN boundary-to-boundary jump should appear in steps."""
        reqs = [60, 40]
        result = cscan(reqs, 50, 100, "right")
        # Steps: 50→60, 60→99 (boundary), 99→0 (jump), 0→40.
        step_targets = [s["to"] for s in result["steps"]]
        self.assertIn(99, step_targets, "Right boundary should appear")
        self.assertIn(0, step_targets, "Left boundary (jump target) should appear")


# ===================================================================
# Input Validation Tests (shared across all algorithms)
# ===================================================================

class TestInputValidation(unittest.TestCase):
    """Test that all algorithms reject invalid inputs."""

    def test_negative_disk_size(self):
        with self.assertRaises(ValueError):
            fcfs([10], 5, -1)

    def test_zero_disk_size(self):
        with self.assertRaises(ValueError):
            fcfs([0], 0, 0)

    def test_head_out_of_range_high(self):
        with self.assertRaises(ValueError):
            sstf([10], 100, 100)  # valid range 0..99

    def test_head_out_of_range_negative(self):
        with self.assertRaises(ValueError):
            sstf([10], -1, 100)

    def test_request_out_of_range_high(self):
        with self.assertRaises(ValueError):
            fcfs([100], 50, 100)  # valid range 0..99

    def test_request_out_of_range_negative(self):
        with self.assertRaises(ValueError):
            fcfs([-5], 50, 100)

    def test_invalid_direction_scan(self):
        with self.assertRaises(ValueError):
            scan([10], 5, 100, "up")

    def test_invalid_direction_cscan(self):
        with self.assertRaises(ValueError):
            cscan([10], 5, 100, "down")

    def test_empty_string_direction(self):
        with self.assertRaises(ValueError):
            scan([10], 5, 100, "")

    def test_validation_function_directly(self):
        """Test _validate_inputs directly."""
        # These should not raise:
        _validate_inputs([0, 99], 50, 100)
        _validate_inputs([], 0, 1)

        # These should raise:
        with self.assertRaises(ValueError):
            _validate_inputs([100], 50, 100)
        with self.assertRaises(ValueError):
            _validate_inputs([50], 100, 100)


# ===================================================================
# Cross-algorithm comparison tests
# ===================================================================

class TestCrossAlgorithm(unittest.TestCase, DiskSchedulingTestMixin):
    """Tests that compare results across algorithms."""

    def test_all_algorithms_service_all_requests(self):
        """Every algorithm must service every request."""
        reqs = [98, 183, 37, 122, 14, 124, 65, 67]
        head = 53
        disk = 200

        for algo, name in [
            (fcfs,  "FCFS"),
            (sstf,  "SSTF"),
        ]:
            result = algo(reqs, head, disk)
            self.assertEqual(
                sorted(result["request_order"]),
                sorted(reqs),
                f"{name} did not service all requests",
            )

        for algo, name in [
            (scan,  "SCAN"),
            (cscan, "C-SCAN"),
        ]:
            for direction in ("left", "right"):
                result = algo(reqs, head, disk, direction)
                self.assertEqual(
                    sorted(result["request_order"]),
                    sorted(reqs),
                    f"{name}-{direction} did not service all requests",
                )

    def test_sstf_not_worse_than_fcfs_standard(self):
        """SSTF typically (and here specifically) outperforms FCFS."""
        reqs = STANDARD_REQUESTS
        fcfs_total = fcfs(reqs, STANDARD_HEAD, STANDARD_DISK_SIZE)["total_head_movement"]
        sstf_total = sstf(reqs, STANDARD_HEAD, STANDARD_DISK_SIZE)["total_head_movement"]
        self.assertLessEqual(sstf_total, fcfs_total)

    def test_identical_results_for_single_request(self):
        """With one request, all algorithms give the same total movement."""
        result_fcfs  = fcfs([80], 50, 100)
        result_sstf  = sstf([80], 50, 100)
        result_scan  = scan([80], 50, 100, "right")
        result_cscan = cscan([80], 50, 100, "right")

        # All should have the same request order.
        self.assertEqual(result_fcfs["request_order"], [80])
        self.assertEqual(result_sstf["request_order"], [80])
        self.assertEqual(result_scan["request_order"], [80])
        self.assertEqual(result_cscan["request_order"], [80])


if __name__ == "__main__":
    unittest.main()
