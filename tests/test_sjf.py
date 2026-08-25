import unittest

from process_concurrency.scheduling.sjf import sjf_schedule


class TestSJF(unittest.TestCase):
    def test_sjf_with_different_arrivals(self):
        processes = [
            {"pid": "P1", "arrival_time": 0, "burst_time": 7},
            {"pid": "P2", "arrival_time": 2, "burst_time": 4},
            {"pid": "P3", "arrival_time": 4, "burst_time": 1},
            {"pid": "P4", "arrival_time": 5, "burst_time": 3},
        ]

        result = sjf_schedule(processes)
        schedule = result["schedule"]

        self.assertEqual([item["pid"] for item in schedule], ["P1", "P3", "P4", "P2"])

        self.assertEqual(schedule[0]["completion_time"], 7)
        self.assertEqual(schedule[1]["completion_time"], 8)
        self.assertEqual(schedule[2]["completion_time"], 11)
        self.assertEqual(schedule[3]["completion_time"], 15)

        self.assertEqual(schedule[0]["turnaround_time"], 7)
        self.assertEqual(schedule[1]["turnaround_time"], 4)
        self.assertEqual(schedule[2]["turnaround_time"], 6)
        self.assertEqual(schedule[3]["turnaround_time"], 13)

        self.assertEqual(schedule[0]["waiting_time"], 0)
        self.assertEqual(schedule[1]["waiting_time"], 3)
        self.assertEqual(schedule[2]["waiting_time"], 3)
        self.assertEqual(schedule[3]["waiting_time"], 9)

        self.assertAlmostEqual(result["average_turnaround_time"], 7.5)
        self.assertAlmostEqual(result["average_waiting_time"], 3.75)


if __name__ == "__main__":
    unittest.main()
