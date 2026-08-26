import unittest

from process_concurrency.deadlock.resource_allocation_graph import ResourceAllocationGraph


class TestResourceAllocationGraph(unittest.TestCase):
    def test_graph_with_no_cycle(self):
        graph = ResourceAllocationGraph()
        graph.add_request_edge("P1", "R1")
        graph.add_allocation_edge("R1", "P2")

        result = graph.detect_cycle()
        self.assertFalse(result["has_cycle"])
        self.assertEqual(result["message"], "No Deadlock Cycle Detected")

    def test_graph_with_cycle(self):
        graph = ResourceAllocationGraph()
        graph.add_request_edge("P1", "R1")
        graph.add_allocation_edge("R1", "P2")
        graph.add_request_edge("P2", "R2")
        graph.add_allocation_edge("R2", "P1")

        result = graph.detect_cycle()
        self.assertTrue(result["has_cycle"])
        self.assertEqual(result["message"], "Potential Deadlock Detected")
        self.assertIn("P1", result["cycle"])
        self.assertIn("P2", result["cycle"])

    def test_multiple_independent_processes_and_resources(self):
        graph = ResourceAllocationGraph()
        graph.add_request_edge("P1", "R1")
        graph.add_allocation_edge("R1", "P2")
        graph.add_request_edge("P3", "R2")
        graph.add_allocation_edge("R2", "P4")

        result = graph.detect_cycle()
        self.assertFalse(result["has_cycle"])

    def test_resource_with_multiple_relationships(self):
        graph = ResourceAllocationGraph()
        graph.add_request_edge("P1", "R1")
        graph.add_allocation_edge("R1", "P2")
        graph.add_request_edge("P2", "R1")

        result = graph.detect_cycle()
        self.assertTrue(result["has_cycle"])
        self.assertEqual(result["message"], "Potential Deadlock Detected")


if __name__ == "__main__":
    unittest.main()
