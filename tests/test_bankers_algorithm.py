import unittest

from process_concurrency.deadlock.bankers_algorithm import bankers_algorithm


class TestBankersAlgorithm(unittest.TestCase):
    def test_safe_state(self):
        available = [3, 3, 2]
        allocation = [
            [0, 1, 0],
            [2, 0, 0],
            [3, 0, 2],
            [2, 1, 1],
        ]
        maximum = [
            [7, 5, 3],
            [3, 2, 2],
            [9, 0, 2],
            [2, 2, 2],
        ]

        result = bankers_algorithm(available, allocation, maximum)
        self.assertTrue(result["safe"])
        self.assertEqual(result["message"], "SAFE")
        self.assertIn("P0", result["safe_sequence"])
        self.assertIn("P1", result["safe_sequence"])

    def test_unsafe_state(self):
        available = [1, 0]
        allocation = [
            [0, 0],
            [1, 0],
        ]
        maximum = [
            [0, 1],
            [1, 0],
        ]

        result = bankers_algorithm(available, allocation, maximum)
        self.assertFalse(result["safe"])
        self.assertEqual(result["message"], "Unsafe State — No Safe Sequence Exists")

    def test_allocation_equals_maximum(self):
        available = [1, 0, 0]
        allocation = [
            [1, 0, 0],
            [0, 0, 0],
        ]
        maximum = [
            [1, 0, 0],
            [0, 0, 0],
        ]

        result = bankers_algorithm(available, allocation, maximum)
        self.assertTrue(result["safe"])
        self.assertEqual(result["message"], "SAFE")

    def test_allocation_greater_than_maximum(self):
        available = [1, 1, 0]
        allocation = [
            [2, 0, 0],
        ]
        maximum = [
            [1, 0, 0],
        ]

        with self.assertRaises(ValueError):
            bankers_algorithm(available, allocation, maximum)

    def test_multiple_processes_and_resource_types(self):
        available = [3, 3, 2]
        allocation = [
            [0, 1, 0],
            [2, 0, 0],
            [3, 0, 2],
            [2, 1, 1],
        ]
        maximum = [
            [7, 5, 3],
            [3, 2, 2],
            [9, 0, 2],
            [2, 2, 2],
        ]

        result = bankers_algorithm(available, allocation, maximum)
        self.assertTrue(result["safe"])
        self.assertIsInstance(result["safe_sequence"], list)
        self.assertIn("P0", result["safe_sequence"])


if __name__ == "__main__":
    unittest.main()
