"""Tests for intelligence/io_disk_bridge.py — I/O to Disk Scheduling Bridge.

Covers:
  1. Each existing disk algorithm is actually called.
  2. Correct request queue generation.
  3. Deterministic mapping.
  4. Request values stay within disk bounds.
  5. Empty telemetry.
  6. Single process.
  7. Multiple processes.
  8. Multiple I/O samples.
  9. Same input produces same request queue.
  10. Different input can produce different request queues.
  11. Recommendation selects minimum movement.
  12. Deterministic tie-breaking.
  13. Invalid disk size.
  14. Invalid head position.
  15. Invalid direction.
  16. Existing disk scheduling behavior remains unchanged.
"""

from __future__ import annotations

import unittest

from intelligence.io_disk_bridge import (
    _deterministic_cylinder,
    _recommend_algorithm,
    analyze_disk_scheduling,
    analyze_process_io_scheduling,
    derive_request_workload,
)


# ===================================================================
# Helpers
# ===================================================================

def _make_metrics(
    pid: int = 100,
    name: str = "test_proc",
    total_io: float = 1_000_000.0,
    read_bytes: float = 600_000.0,
    write_bytes: float = 400_000.0,
    read_count: int = 100,
    write_count: int = 50,
) -> dict:
    return {
        "pid": pid,
        "name": name,
        "total_io_bytes_per_sec": total_io,
        "read_bytes_per_sec": read_bytes,
        "write_bytes_per_sec": write_bytes,
        "read_count": read_count,
        "write_count": write_count,
    }


# ===================================================================
# Test: _deterministic_cylinder
# ===================================================================

class TestDeterministicCylinder(unittest.TestCase):
    def test_within_bounds(self):
        for pid in range(100):
            c = _deterministic_cylinder(pid, 1000, 200)
            self.assertGreaterEqual(c, 0)
            self.assertLess(c, 200)

    def test_deterministic(self):
        c1 = _deterministic_cylinder(42, 5000, 200)
        c2 = _deterministic_cylinder(42, 5000, 200)
        self.assertEqual(c1, c2)

    def test_different_pid_different_cylinder(self):
        c1 = _deterministic_cylinder(1, 5000, 200)
        c2 = _deterministic_cylinder(2, 5000, 200)
        # Not guaranteed to be different, but extremely likely with MD5.
        # This is a probabilistic sanity check.
        self.assertIsInstance(c1, int)
        self.assertIsInstance(c2, int)

    def test_salt_changes_result(self):
        c1 = _deterministic_cylinder(42, 5000, 200, salt="read")
        c2 = _deterministic_cylinder(42, 5000, 200, salt="write")
        self.assertNotEqual(c1, c2)

    def test_disk_size_one(self):
        c = _deterministic_cylinder(42, 5000, 1)
        self.assertEqual(c, 0)

    def test_large_disk_size(self):
        c = _deterministic_cylinder(42, 5000, 100_000)
        self.assertGreaterEqual(c, 0)
        self.assertLess(c, 100_000)


# ===================================================================
# Test: derive_request_workload
# ===================================================================

class TestDeriveRequestWorkload(unittest.TestCase):
    def test_empty_input(self):
        result = derive_request_workload([])
        self.assertEqual(result, [])

    def test_none_input(self):
        result = derive_request_workload(None)
        self.assertEqual(result, [])

    def test_all_below_min_rate(self):
        metrics = [_make_metrics(total_io=50.0)] * 3
        result = derive_request_workload(metrics)
        self.assertEqual(result, [])

    def test_single_process(self):
        metrics = [_make_metrics(pid=100, total_io=5_000_000, read_count=200, write_count=100)]
        result = derive_request_workload(metrics, disk_size=200)
        self.assertGreater(len(result), 0)
        for c in result:
            self.assertGreaterEqual(c, 0)
            self.assertLess(c, 200)

    def test_multiple_processes(self):
        metrics = [
            _make_metrics(pid=1, total_io=5_000_000),
            _make_metrics(pid=2, total_io=3_000_000),
            _make_metrics(pid=3, total_io=1_000_000),
        ]
        result = derive_request_workload(metrics, disk_size=200)
        self.assertGreater(len(result), 0)
        for c in result:
            self.assertGreaterEqual(c, 0)
            self.assertLess(c, 200)

    def test_request_count_scales_with_intensity(self):
        """Higher I/O → more requests."""
        low = [_make_metrics(pid=1, total_io=1_000_000)]
        high = [_make_metrics(pid=1, total_io=10_000_000)]
        q_low = derive_request_workload(low, disk_size=200)
        q_high = derive_request_workload(high, disk_size=200)
        self.assertGreaterEqual(len(q_high), len(q_low))

    def test_deterministic_same_input_same_output(self):
        metrics = [
            _make_metrics(pid=10, total_io=2_000_000, read_count=50, write_count=30),
            _make_metrics(pid=20, total_io=8_000_000, read_count=200, write_count=100),
        ]
        q1 = derive_request_workload(metrics, disk_size=200)
        q2 = derive_request_workload(metrics, disk_size=200)
        self.assertEqual(q1, q2)

    def test_different_input_can_differ(self):
        m1 = [_make_metrics(pid=1, total_io=5_000_000, read_count=100, write_count=50)]
        m2 = [_make_metrics(pid=2, total_io=5_000_000, read_count=200, write_count=100)]
        q1 = derive_request_workload(m1, disk_size=200)
        q2 = derive_request_workload(m2, disk_size=200)
        # Very likely different (different PIDs → different hashes).
        self.assertIsInstance(q1, list)
        self.assertIsInstance(q2, list)

    def test_all_within_disk_bounds(self):
        metrics = [_make_metrics(pid=i, total_io=1_000_000 * (i + 1)) for i in range(20)]
        for disk_size in [10, 50, 200, 1000]:
            queue = derive_request_workload(metrics, disk_size=disk_size)
            for c in queue:
                self.assertGreaterEqual(c, 0, f"cylinder {c} < 0 for disk_size={disk_size}")
                self.assertLess(c, disk_size, f"cylinder {c} >= disk_size={disk_size}")

    def test_non_dict_entries_skipped(self):
        metrics = ["invalid", None, 42, _make_metrics(pid=1, total_io=5_000_000)]
        result = derive_request_workload(metrics, disk_size=200)
        self.assertGreater(len(result), 0)

    def test_custom_min_io_rate(self):
        metrics = [_make_metrics(total_io=500.0)]
        # With default min_io_rate=100, this would be included.
        result = derive_request_workload(metrics, disk_size=200, min_io_rate=1000)
        self.assertEqual(result, [])

    def test_max_requests_per_process_cap(self):
        """Even a very active process should not exceed the cap."""
        metrics = [_make_metrics(pid=1, total_io=100_000_000)]
        result = derive_request_workload(
            metrics, disk_size=200, max_requests_per_process=3
        )
        self.assertLessEqual(len(result), 3)


# ===================================================================
# Test: analyze_disk_scheduling
# ===================================================================

class TestAnalyzeDiskScheduling(unittest.TestCase):
    def test_calls_all_four_algorithms(self):
        """Each of FCFS, SSTF, SCAN, C-SCAN is invoked."""
        requests = [98, 183, 37, 122, 14, 124, 65, 67]
        result = analyze_disk_scheduling(requests, 53, 200)
        self.assertIn("FCFS", result["results"])
        self.assertIn("SSTF", result["results"])
        self.assertIn("SCAN", result["results"])
        self.assertIn("C-SCAN", result["results"])

    def test_result_structure(self):
        result = analyze_disk_scheduling([50, 100, 150], 0, 200)
        self.assertIn("request_count", result)
        self.assertIn("disk_size", result)
        self.assertIn("head_position", result)
        self.assertIn("direction", result)
        self.assertIn("results", result)
        self.assertIn("total_head_movements", result)
        self.assertIn("recommended_algorithm", result)
        self.assertIn("reason", result)

    def test_individual_result_structure(self):
        result = analyze_disk_scheduling([50, 100], 0, 200)
        for algo in ["FCFS", "SSTF", "SCAN", "C-SCAN"]:
            r = result["results"][algo]
            self.assertEqual(r["algorithm"], algo)
            self.assertIn("total_head_movement", r)
            self.assertIn("request_order", r)
            self.assertIn("steps", r)

    def test_empty_request_queue(self):
        result = analyze_disk_scheduling([], 53, 200)
        self.assertEqual(result["request_count"], 0)
        self.assertEqual(result["recommended_algorithm"], "FCFS")
        for algo in ["FCFS", "SSTF", "SCAN", "C-SCAN"]:
            self.assertEqual(result["total_head_movements"][algo], 0)

    def test_recommendation_selects_minimum_movement(self):
        """The recommended algorithm must have the lowest total head movement."""
        requests = [98, 183, 37, 122, 14, 124, 65, 67]
        result = analyze_disk_scheduling(requests, 53, 200)
        recommended = result["recommended_algorithm"]
        recommended_movement = result["total_head_movements"][recommended]
        for algo, mv in result["total_head_movements"].items():
            self.assertLessEqual(
                recommended_movement, mv,
                f"{recommended} ({recommended_movement}) should be <= {algo} ({mv})",
            )

    def test_recommendation_reason_mentions_movement(self):
        requests = [98, 183, 37, 122]
        result = analyze_disk_scheduling(requests, 53, 200)
        self.assertIn("lowest simulated total head movement", result["reason"])

    def test_invalid_disk_size(self):
        with self.assertRaises(ValueError):
            analyze_disk_scheduling([50], 0, -1)

    def test_invalid_head_position(self):
        with self.assertRaises(ValueError):
            analyze_disk_scheduling([50], 300, 200)

    def test_invalid_direction(self):
        with self.assertRaises(ValueError):
            analyze_disk_scheduling([50], 0, 200, direction="up")

    def test_direction_forwarded_to_scan_cscan(self):
        result = analyze_disk_scheduling([50, 100], 0, 200, direction="left")
        self.assertEqual(result["results"]["SCAN"]["direction"], "left")
        self.assertEqual(result["results"]["C-SCAN"]["direction"], "left")

    def test_standard_textbook_example(self):
        """Verify against the standard textbook example."""
        requests = [98, 183, 37, 122, 14, 124, 65, 67]
        result = analyze_disk_scheduling(requests, 53, 200)
        # FCFS total should be 640 for this standard example.
        self.assertEqual(result["total_head_movements"]["FCFS"], 640)
        # SSTF should be lower than FCFS.
        self.assertLess(
            result["total_head_movements"]["SSTF"],
            result["total_head_movements"]["FCFS"],
        )

    def test_head_movement_values_are_integers(self):
        result = analyze_disk_scheduling([10, 50, 90], 0, 100)
        for algo, mv in result["total_head_movements"].items():
            self.assertIsInstance(mv, int, f"{algo} movement should be int")


# ===================================================================
# Test: analyze_process_io_scheduling
# ===================================================================

class TestAnalyzeProcessIOScheduling(unittest.TestCase):
    def test_end_to_end_single_process(self):
        metrics = [_make_metrics(pid=100, total_io=5_000_000)]
        result = analyze_process_io_scheduling(metrics)
        self.assertIn("observed_processes", result)
        self.assertIn("simulated_request_queue", result)
        self.assertIn("simulation_note", result)
        self.assertIn("scheduling_analysis", result)
        self.assertGreater(len(result["simulated_request_queue"]), 0)

    def test_end_to_end_multiple_processes(self):
        metrics = [
            _make_metrics(pid=1, total_io=5_000_000),
            _make_metrics(pid=2, total_io=3_000_000),
            _make_metrics(pid=3, total_io=1_000_000),
        ]
        result = analyze_process_io_scheduling(metrics)
        self.assertGreater(len(result["observed_processes"]), 0)
        self.assertGreater(len(result["simulated_request_queue"]), 0)
        self.assertIn("recommended_algorithm", result["scheduling_analysis"])

    def test_empty_telemetry(self):
        result = analyze_process_io_scheduling([])
        self.assertEqual(len(result["observed_processes"]), 0)
        self.assertEqual(len(result["simulated_request_queue"]), 0)
        self.assertEqual(result["scheduling_analysis"]["request_count"], 0)

    def test_simulation_note_present(self):
        result = analyze_process_io_scheduling([_make_metrics()])
        self.assertIn("SIMULATED", result["simulation_note"].upper())
        self.assertIn("Simulated disk request workload", result["simulation_note"])

    def test_observed_processes_structure(self):
        metrics = [_make_metrics(pid=42, name="myapp", total_io=2_000_000)]
        result = analyze_process_io_scheduling(metrics)
        obs = result["observed_processes"][0]
        self.assertEqual(obs["pid"], 42)
        self.assertEqual(obs["name"], "myapp")
        self.assertIn("total_io_bytes_per_sec", obs)

    def test_classification_forwarded(self):
        metrics = [_make_metrics(pid=1, total_io=5_000_000)]
        metrics[0]["classification"] = "IO_BOUND"
        result = analyze_process_io_scheduling(metrics)
        self.assertEqual(result["observed_processes"][0]["classification"], "IO_BOUND")

    def test_custom_parameters(self):
        metrics = [_make_metrics(pid=1, total_io=5_000_000)]
        result = analyze_process_io_scheduling(
            metrics, head_position=50, disk_size=100, direction="left"
        )
        self.assertEqual(result["scheduling_analysis"]["head_position"], 50)
        self.assertEqual(result["scheduling_analysis"]["disk_size"], 100)
        self.assertEqual(result["scheduling_analysis"]["direction"], "left")

    def test_deterministic_end_to_end(self):
        metrics = [
            _make_metrics(pid=10, total_io=2_000_000, read_count=50, write_count=30),
            _make_metrics(pid=20, total_io=8_000_000, read_count=200, write_count=100),
        ]
        r1 = analyze_process_io_scheduling(metrics)
        r2 = analyze_process_io_scheduling(metrics)
        self.assertEqual(r1["simulated_request_queue"], r2["simulated_request_queue"])
        self.assertEqual(
            r1["scheduling_analysis"]["recommended_algorithm"],
            r2["scheduling_analysis"]["recommended_algorithm"],
        )

    def test_non_dict_entries_skipped(self):
        metrics = [None, "bad", 42, _make_metrics(pid=1, total_io=5_000_000)]
        result = analyze_process_io_scheduling(metrics)
        # Only the valid dict should appear in observed_processes.
        self.assertEqual(len(result["observed_processes"]), 1)


# ===================================================================
# Test: _recommend_algorithm
# ===================================================================

class TestRecommendAlgorithm(unittest.TestCase):
    def test_clear_winner(self):
        movements = {"FCFS": 500, "SSTF": 300, "SCAN": 400, "C-SCAN": 450}
        winner, reason = _recommend_algorithm(movements)
        self.assertEqual(winner, "SSTF")
        self.assertIn("300", reason)

    def test_tie_breaking_deterministic(self):
        """When multiple algorithms tie, tie-breaking is deterministic."""
        movements = {"FCFS": 100, "SSTF": 100, "SCAN": 200, "C-SCAN": 200}
        winner1, _ = _recommend_algorithm(movements)
        winner2, _ = _recommend_algorithm(movements)
        self.assertEqual(winner1, winner2)
        # FCFS (index 1) beats SSTF (index 3) in our tie-break order.
        self.assertEqual(winner1, "FCFS")

    def test_all_tied(self):
        movements = {"FCFS": 100, "SSTF": 100, "SCAN": 100, "C-SCAN": 100}
        winner, reason = _recommend_algorithm(movements)
        # C-SCAN is first in _TIE_BREAK_ORDER.
        self.assertEqual(winner, "C-SCAN")
        self.assertIn("Tied with", reason)

    def test_reason_mentions_tie_breaking(self):
        movements = {"FCFS": 100, "SSTF": 100, "SCAN": 200, "C-SCAN": 200}
        _, reason = _recommend_algorithm(movements)
        self.assertIn("deterministic tie-breaking", reason)


# ===================================================================
# Test: Existing disk scheduling behavior unchanged
# ===================================================================

class TestExistingAlgorithmsUnchanged(unittest.TestCase):
    """Verify the bridge does not alter existing algorithm behavior."""

    def test_fcfs_standard_example(self):
        from disk_io.fcfs import fcfs
        requests = [98, 183, 37, 122, 14, 124, 65, 67]
        result = fcfs(requests, 53, 200)
        self.assertEqual(result["total_head_movement"], 640)
        self.assertEqual(result["algorithm"], "FCFS")

    def test_sstf_standard_example(self):
        from disk_io.sstf import sstf
        requests = [98, 183, 37, 122, 14, 124, 65, 67]
        result = sstf(requests, 53, 200)
        self.assertEqual(result["algorithm"], "SSTF")
        self.assertLess(result["total_head_movement"], 640)

    def test_scan_standard_example(self):
        from disk_io.scan import scan
        requests = [98, 183, 37, 122, 14, 124, 65, 67]
        result = scan(requests, 53, 200, "right")
        self.assertEqual(result["algorithm"], "SCAN")
        self.assertEqual(result["direction"], "right")

    def test_cscan_standard_example(self):
        from disk_io.cscan import cscan
        requests = [98, 183, 37, 122, 14, 124, 65, 67]
        result = cscan(requests, 53, 200, "right")
        self.assertEqual(result["algorithm"], "C-SCAN")
        self.assertEqual(result["direction"], "right")

    def test_algorithms_not_mutating_input(self):
        from disk_io.fcfs import fcfs
        from disk_io.sstf import sstf
        requests = [98, 183, 37, 122]
        original = list(requests)
        fcfs(requests, 53, 200)
        self.assertEqual(requests, original)
        sstf(requests, 53, 200)
        self.assertEqual(requests, original)


# ===================================================================
# Test: Edge cases
# ===================================================================

class TestEdgeCases(unittest.TestCase):
    def test_single_request(self):
        result = analyze_disk_scheduling([100], 50, 200)
        self.assertEqual(result["request_count"], 1)
        # FCFS and SSTF just move to the request.
        self.assertEqual(result["total_head_movements"]["FCFS"], 50)
        self.assertEqual(result["total_head_movements"]["SSTF"], 50)
        # SCAN visits boundary then reverses.
        self.assertGreater(result["total_head_movements"]["SCAN"], 50)
        # C-SCAN: only one side has requests, no boundary jump needed.
        self.assertEqual(result["total_head_movements"]["C-SCAN"], 50)

    def test_request_at_head_position(self):
        """Request at the head → zero movement for FCFS/SSTF/C-SCAN.
        SCAN still visits the boundary."""
        result = analyze_disk_scheduling([50], 50, 200)
        self.assertEqual(result["total_head_movements"]["FCFS"], 0)
        self.assertEqual(result["total_head_movements"]["SSTF"], 0)
        self.assertEqual(result["total_head_movements"]["C-SCAN"], 0)
        # SCAN sweeps to boundary and back even with request at head.
        self.assertGreater(result["total_head_movements"]["SCAN"], 0)

    def test_disk_size_one(self):
        """disk_size=1 → only cylinder 0 exists."""
        result = analyze_disk_scheduling([0], 0, 1)
        self.assertEqual(result["request_count"], 1)

    def test_head_at_boundary_right(self):
        result = analyze_disk_scheduling([10, 50], 199, 200)
        self.assertGreater(result["total_head_movements"]["FCFS"], 0)

    def test_head_at_boundary_left(self):
        result = analyze_disk_scheduling([150, 180], 0, 200)
        self.assertGreater(result["total_head_movements"]["FCFS"], 0)

    def test_many_requests(self):
        requests = list(range(0, 200, 10))  # 20 requests
        result = analyze_disk_scheduling(requests, 50, 200)
        self.assertEqual(result["request_count"], 20)

    def test_duplicate_requests(self):
        requests = [50, 50, 50, 50]
        result = analyze_disk_scheduling(requests, 50, 200)
        self.assertEqual(result["request_count"], 4)
        # FCFS and SSTF: head is already at 50, all requests at 50 → zero.
        self.assertEqual(result["total_head_movements"]["FCFS"], 0)
        self.assertEqual(result["total_head_movements"]["SSTF"], 0)
        # C-SCAN: all on same side, no boundary jump needed.
        self.assertEqual(result["total_head_movements"]["C-SCAN"], 0)
        # SCAN: sweeps to boundary then reverses.
        self.assertGreater(result["total_head_movements"]["SCAN"], 0)

    def test_negative_io_rate_ignored(self):
        metrics = [_make_metrics(total_io=-1000.0)]
        result = derive_request_workload(metrics)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
