import unittest

from process_concurrency.scheduling.fcfs import fcfs_schedule


class TestFCFS(unittest.TestCase):
    def test_fcfs_example(self):
        processes = [
            {"pid": "P1", "arrival_time": 0, "burst_time": 5},
            {"pid": "P2", "arrival_time": 1, "burst_time": 3},
            {"pid": "P3", "arrival_time": 2, "burst_time": 2},
        ]

        result = fcfs_schedule(processes)
        schedule = result["schedule"]

        self.assertEqual(schedule[0]["completion_time"], 5)
        self.assertEqual(schedule[1]["completion_time"], 8)
        self.assertEqual(schedule[2]["completion_time"], 10)

        self.assertEqual(schedule[0]["turnaround_time"], 5)
        self.assertEqual(schedule[1]["turnaround_time"], 7)
        self.assertEqual(schedule[2]["turnaround_time"], 8)

        self.assertEqual(schedule[0]["waiting_time"], 0)
        self.assertEqual(schedule[1]["waiting_time"], 4)
        self.assertEqual(schedule[2]["waiting_time"], 6)

        self.assertAlmostEqual(result["average_turnaround_time"], 20 / 3)
        self.assertAlmostEqual(result["average_waiting_time"], 10 / 3)


if __name__ == "__main__":
    unittest.main()
