import os
import unittest

from process_concurrency.scheduling.integration import build_visualization, schedule_processes


class TestSchedulingIntegration(unittest.TestCase):
    def test_fcfs_integration(self):
        processes = [
            {"pid": "P1", "arrival_time": 0, "burst_time": 5},
            {"pid": "P2", "arrival_time": 1, "burst_time": 3},
            {"pid": "P3", "arrival_time": 2, "burst_time": 2},
        ]

        result = schedule_processes("fcfs", processes)
        self.assertEqual(result["execution_sequence"], ["P1", "P2", "P3"])
        self.assertIn("gantt_segments", result)
        self.assertGreater(len(result["gantt_segments"]), 0)

    def test_round_robin_integration(self):
        processes = [
            {"pid": "P1", "arrival_time": 0, "burst_time": 5},
            {"pid": "P2", "arrival_time": 1, "burst_time": 3},
            {"pid": "P3", "arrival_time": 2, "burst_time": 2},
        ]

        result = schedule_processes("round_robin", processes, time_quantum=2)
        self.assertEqual(result["execution_sequence"], ["P1", "P2", "P3", "P1", "P2", "P1"])
        self.assertIn("gantt_segments", result)
        self.assertGreater(len(result["gantt_segments"]), 0)

    def test_gantt_chart_generation(self):
        processes = [
            {"pid": "P1", "arrival_time": 0, "burst_time": 5},
            {"pid": "P2", "arrival_time": 1, "burst_time": 3},
            {"pid": "P3", "arrival_time": 2, "burst_time": 2},
        ]

        result = build_visualization("fcfs", processes, save_path="test_gantt.png")
        self.assertIn("figure", result)
        self.assertTrue(os.path.exists("test_gantt.png"))
        os.remove("test_gantt.png")


if __name__ == "__main__":
    unittest.main()
