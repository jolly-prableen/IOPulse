import unittest

from process_concurrency.scheduling.round_robin import round_robin_schedule


class TestRoundRobin(unittest.TestCase):
    def test_same_arrival_time(self):
        processes = [
            {"pid": "P1", "arrival_time": 0, "burst_time": 5},
            {"pid": "P2", "arrival_time": 0, "burst_time": 3},
            {"pid": "P3", "arrival_time": 0, "burst_time": 2},
        ]

        result = round_robin_schedule(processes, time_quantum=2)
        schedule = result["schedule"]

        self.assertEqual(result["execution_sequence"], ["P1", "P2", "P3", "P1", "P2", "P1"])
        self.assertEqual([item["pid"] for item in schedule], ["P1", "P2", "P3"])
        self.assertEqual(schedule[0]["completion_time"], 10)
        self.assertEqual(schedule[1]["completion_time"], 9)
        self.assertEqual(schedule[2]["completion_time"], 6)
        self.assertAlmostEqual(result["average_turnaround_time"], 25 / 3)
        self.assertAlmostEqual(result["average_waiting_time"], 5.0)

    def test_different_arrival_times(self):
        processes = [
            {"pid": "P1", "arrival_time": 0, "burst_time": 5},
            {"pid": "P2", "arrival_time": 1, "burst_time": 3},
            {"pid": "P3", "arrival_time": 2, "burst_time": 2},
        ]

        result = round_robin_schedule(processes, time_quantum=2)
        schedule = result["schedule"]

        self.assertEqual(result["execution_sequence"], ["P1", "P2", "P3", "P1", "P2", "P1"])
        self.assertEqual([item["pid"] for item in schedule], ["P1", "P2", "P3"])
        self.assertEqual(schedule[0]["completion_time"], 10)
        self.assertEqual(schedule[1]["completion_time"], 9)
        self.assertEqual(schedule[2]["completion_time"], 6)
        self.assertAlmostEqual(result["average_turnaround_time"], 22 / 3)
        self.assertAlmostEqual(result["average_waiting_time"], 4.0)

    def test_burst_smaller_than_quantum(self):
        processes = [
            {"pid": "P1", "arrival_time": 0, "burst_time": 1},
            {"pid": "P2", "arrival_time": 0, "burst_time": 4},
        ]

        result = round_robin_schedule(processes, time_quantum=3)
        schedule = result["schedule"]

        self.assertEqual(result["execution_sequence"], ["P1", "P2", "P2"])
        self.assertEqual(schedule[0]["completion_time"], 1)
        self.assertEqual(schedule[1]["completion_time"], 5)
        self.assertAlmostEqual(result["average_turnaround_time"], 3.0)
        self.assertAlmostEqual(result["average_waiting_time"], 0.5)

    def test_multiple_rounds(self):
        processes = [
            {"pid": "P1", "arrival_time": 0, "burst_time": 6},
            {"pid": "P2", "arrival_time": 0, "burst_time": 4},
        ]

        result = round_robin_schedule(processes, time_quantum=2)

        self.assertEqual(result["execution_sequence"], ["P1", "P2", "P1", "P2", "P1"])
        self.assertEqual([item["pid"] for item in result["schedule"]], ["P1", "P2"])
        self.assertEqual(result["schedule"][0]["completion_time"], 10)
        self.assertEqual(result["schedule"][1]["completion_time"], 8)
        self.assertAlmostEqual(result["average_turnaround_time"], 9.0)
        self.assertAlmostEqual(result["average_waiting_time"], 4.0)


if __name__ == "__main__":
    unittest.main()
