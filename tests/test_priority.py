import unittest

from process_concurrency.scheduling.priority import priority_schedule


class TestPriority(unittest.TestCase):
    def test_priority_with_arrivals_and_ties(self):
        processes = [
            {"pid": "P1", "arrival_time": 0, "burst_time": 5, "priority": 2},
            {"pid": "P2", "arrival_time": 1, "burst_time": 3, "priority": 1},
            {"pid": "P3", "arrival_time": 2, "burst_time": 2, "priority": 4},
            {"pid": "P4", "arrival_time": 3, "burst_time": 1, "priority": 3},
            {"pid": "P5", "arrival_time": 4, "burst_time": 2, "priority": 1},
        ]

        result = priority_schedule(processes)
        schedule = result["schedule"]

        self.assertEqual([item["pid"] for item in schedule], ["P1", "P2", "P5", "P4", "P3"])

        self.assertEqual(schedule[0]["completion_time"], 5)
        self.assertEqual(schedule[1]["completion_time"], 8)
        self.assertEqual(schedule[2]["completion_time"], 10)
        self.assertEqual(schedule[3]["completion_time"], 11)
        self.assertEqual(schedule[4]["completion_time"], 13)

        self.assertEqual(schedule[0]["turnaround_time"], 5)
        self.assertEqual(schedule[1]["turnaround_time"], 7)
        self.assertEqual(schedule[2]["turnaround_time"], 6)
        self.assertEqual(schedule[3]["turnaround_time"], 8)
        self.assertEqual(schedule[4]["turnaround_time"], 11)

        self.assertEqual(schedule[0]["waiting_time"], 0)
        self.assertEqual(schedule[1]["waiting_time"], 4)
        self.assertEqual(schedule[2]["waiting_time"], 4)
        self.assertEqual(schedule[3]["waiting_time"], 7)
        self.assertEqual(schedule[4]["waiting_time"], 9)

        self.assertAlmostEqual(result["average_turnaround_time"], 7.4)
        self.assertAlmostEqual(result["average_waiting_time"], 4.8)


if __name__ == "__main__":
    unittest.main()
