"""
tests/test_page_replacement.py – Unit tests for memory/page_replacement.py
OS Sentinel – Teammate B

Tests cover:
  1. Normal reference strings
  2. Repeated pages (all hits after initial load)
  3. More unique pages than available frames
  4. Edge case: only 1 frame
  5. A case where FIFO, LRU, and Optimal produce different fault counts
  6. Structural validation (keys, types, invariant: faults + hits == len(pages))
  7. No mutation of the original page list
"""

import unittest
from memory.page_replacement import fifo, lru, optimal, compare_algorithms


# -----------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------

def assert_result_structure(test_case: unittest.TestCase, result: dict, algorithm: str, pages: list):
    """Validate the shape and invariants of a result dict."""
    # Top-level keys
    for key in ("algorithm", "page_faults", "page_hits", "fault_rate", "hit_rate", "steps"):
        test_case.assertIn(key, result, f"Missing key '{key}' in result")

    test_case.assertEqual(result["algorithm"], algorithm)

    # Invariant: faults + hits == total pages
    total = len(pages)
    test_case.assertEqual(
        result["page_faults"] + result["page_hits"], total,
        "page_faults + page_hits must equal len(pages)"
    )

    # Rates should be consistent
    if total > 0:
        test_case.assertAlmostEqual(result["fault_rate"], result["page_faults"] / total, places=4)
        test_case.assertAlmostEqual(result["hit_rate"],   result["page_hits"]   / total, places=4)

    # Steps length
    test_case.assertEqual(len(result["steps"]), total)

    # Each step must have the right keys and types
    for step in result["steps"]:
        test_case.assertIn("page", step)
        test_case.assertIn("frames", step)
        test_case.assertIn("hit", step)
        test_case.assertIn("fault", step)
        test_case.assertIsInstance(step["frames"], list)
        test_case.assertIsInstance(step["hit"], bool)
        test_case.assertIsInstance(step["fault"], bool)
        # hit and fault must be opposite of each other
        test_case.assertNotEqual(step["hit"], step["fault"])


# =======================================================================
# FIFO Tests
# =======================================================================

class TestFIFO(unittest.TestCase):
    """Tests for the FIFO page replacement algorithm."""

    def test_normal_reference_string(self):
        """Classic textbook example: pages=[7,0,1,2,0,3,0,4,2,3,0,3,2,1,2,0,1,7,0,1], frames=3."""
        pages = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
        result = fifo(pages, 3)
        assert_result_structure(self, result, "FIFO", pages)
        self.assertEqual(result["page_faults"], 15)
        self.assertEqual(result["page_hits"], 5)

    def test_repeated_pages(self):
        """If the same page is repeated, only the first access faults (within frame capacity)."""
        pages = [1, 1, 1, 1, 1]
        result = fifo(pages, 3)
        assert_result_structure(self, result, "FIFO", pages)
        self.assertEqual(result["page_faults"], 1)
        self.assertEqual(result["page_hits"], 4)

    def test_more_pages_than_frames(self):
        """All unique pages with only 2 frames — every new page causes a fault."""
        pages = [1, 2, 3, 4, 5]
        result = fifo(pages, 2)
        assert_result_structure(self, result, "FIFO", pages)
        self.assertEqual(result["page_faults"], 5)
        self.assertEqual(result["page_hits"], 0)

    def test_single_frame(self):
        """With only 1 frame, every new page faults and hits only happen on consecutive repeats."""
        pages = [1, 2, 2, 3, 1]
        result = fifo(pages, 1)
        assert_result_structure(self, result, "FIFO", pages)
        self.assertEqual(result["page_faults"], 4)
        self.assertEqual(result["page_hits"], 1)

    def test_frame_states_step_by_step(self):
        """Verify the exact frame contents at each step."""
        pages = [1, 2, 3, 1, 4]
        result = fifo(pages, 3)

        expected_frames = [
            [1, None, None],    # Load 1 into frame 0
            [1, 2, None],       # Load 2 into frame 1
            [1, 2, 3],          # Load 3 into frame 2
            [1, 2, 3],          # Hit on 1 (already in frame 0)
            [4, 2, 3],          # Fault: replace frame 0 (FIFO oldest = 1) → 4
        ]
        expected_faults = [True, True, True, False, True]

        for i, step in enumerate(result["steps"]):
            self.assertEqual(step["frames"], expected_frames[i], f"Step {i}")
            self.assertEqual(step["fault"], expected_faults[i], f"Step {i} fault")

    def test_no_mutation_of_input(self):
        """The original page list must not be modified."""
        pages = [1, 2, 3, 4]
        pages_copy = list(pages)
        fifo(pages, 2)
        self.assertEqual(pages, pages_copy)

    def test_simple_example(self):
        """Simple case: pages=[1,2,3,1,4,5,2,1], frames=3."""
        pages = [1, 2, 3, 1, 4, 5, 2, 1]
        result = fifo(pages, 3)
        assert_result_structure(self, result, "FIFO", pages)
        # Step-by-step:
        #   1 → [1, -, -]  FAULT
        #   2 → [1, 2, -]  FAULT
        #   3 → [1, 2, 3]  FAULT
        #   1 → [1, 2, 3]  HIT
        #   4 → [4, 2, 3]  FAULT (replace frame 0, oldest=1)
        #   5 → [4, 5, 3]  FAULT (replace frame 1, oldest=2)
        #   2 → [4, 5, 2]  FAULT (replace frame 2, oldest=3)
        #   1 → [1, 5, 2]  FAULT (replace frame 0, oldest=4)
        self.assertEqual(result["page_faults"], 7)
        self.assertEqual(result["page_hits"], 1)


# =======================================================================
# LRU Tests
# =======================================================================

class TestLRU(unittest.TestCase):
    """Tests for the LRU page replacement algorithm."""

    def test_normal_reference_string(self):
        """Classic textbook example."""
        pages = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
        result = lru(pages, 3)
        assert_result_structure(self, result, "LRU", pages)
        self.assertEqual(result["page_faults"], 12)
        self.assertEqual(result["page_hits"], 8)

    def test_repeated_pages(self):
        pages = [1, 1, 1, 1, 1]
        result = lru(pages, 3)
        assert_result_structure(self, result, "LRU", pages)
        self.assertEqual(result["page_faults"], 1)
        self.assertEqual(result["page_hits"], 4)

    def test_more_pages_than_frames(self):
        pages = [1, 2, 3, 4, 5]
        result = lru(pages, 2)
        assert_result_structure(self, result, "LRU", pages)
        self.assertEqual(result["page_faults"], 5)
        self.assertEqual(result["page_hits"], 0)

    def test_single_frame(self):
        pages = [1, 2, 2, 3, 1]
        result = lru(pages, 1)
        assert_result_structure(self, result, "LRU", pages)
        self.assertEqual(result["page_faults"], 4)
        self.assertEqual(result["page_hits"], 1)

    def test_frame_states_step_by_step(self):
        """LRU replaces based on recency of USE, not insertion order."""
        pages = [1, 2, 3, 1, 4]
        result = lru(pages, 3)

        expected_frames = [
            [1, None, None],    # Load 1
            [1, 2, None],       # Load 2
            [1, 2, 3],          # Load 3
            [1, 2, 3],          # Hit on 1 → 1 becomes most-recently-used
            [1, 4, 3],          # Fault: LRU is 2 (used at step 1) → replace with 4
        ]
        expected_faults = [True, True, True, False, True]

        for i, step in enumerate(result["steps"]):
            self.assertEqual(step["frames"], expected_frames[i], f"Step {i}")
            self.assertEqual(step["fault"], expected_faults[i], f"Step {i} fault")

    def test_no_mutation_of_input(self):
        pages = [1, 2, 3, 4]
        pages_copy = list(pages)
        lru(pages, 2)
        self.assertEqual(pages, pages_copy)

    def test_simple_example(self):
        """pages=[1,2,3,1,4,5,2,1], frames=3."""
        pages = [1, 2, 3, 1, 4, 5, 2, 1]
        result = lru(pages, 3)
        assert_result_structure(self, result, "LRU", pages)
        # Step-by-step:
        #   1 → [1, -, -]  FAULT
        #   2 → [1, 2, -]  FAULT
        #   3 → [1, 2, 3]  FAULT
        #   1 → [1, 2, 3]  HIT   (1 refreshed)
        #   4 → [1, 4, 3]  FAULT (LRU=2 at step 1)
        #   5 → [1, 4, 5]  FAULT (LRU=3 at step 2)
        #   2 → [2, 4, 5]  FAULT (LRU=1 at step 3)
        #   1 → [2, 1, 5]  FAULT (LRU=4 at step 4)
        self.assertEqual(result["page_faults"], 7)
        self.assertEqual(result["page_hits"], 1)


# =======================================================================
# Optimal Tests
# =======================================================================

class TestOptimal(unittest.TestCase):
    """Tests for the Optimal (Bélády's) page replacement algorithm."""

    def test_normal_reference_string(self):
        """Classic textbook example — Optimal should beat FIFO and LRU."""
        pages = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
        result = optimal(pages, 3)
        assert_result_structure(self, result, "Optimal", pages)
        self.assertEqual(result["page_faults"], 9)
        self.assertEqual(result["page_hits"], 11)

    def test_repeated_pages(self):
        pages = [1, 1, 1, 1, 1]
        result = optimal(pages, 3)
        assert_result_structure(self, result, "Optimal", pages)
        self.assertEqual(result["page_faults"], 1)
        self.assertEqual(result["page_hits"], 4)

    def test_more_pages_than_frames(self):
        pages = [1, 2, 3, 4, 5]
        result = optimal(pages, 2)
        assert_result_structure(self, result, "Optimal", pages)
        self.assertEqual(result["page_faults"], 5)
        self.assertEqual(result["page_hits"], 0)

    def test_single_frame(self):
        pages = [1, 2, 2, 3, 1]
        result = optimal(pages, 1)
        assert_result_structure(self, result, "Optimal", pages)
        self.assertEqual(result["page_faults"], 4)
        self.assertEqual(result["page_hits"], 1)

    def test_frame_states_step_by_step(self):
        """Optimal looks ahead to decide the victim."""
        pages = [1, 2, 3, 1, 4]
        result = optimal(pages, 3)

        expected_frames = [
            [1, None, None],    # Load 1
            [1, 2, None],       # Load 2
            [1, 2, 3],          # Load 3
            [1, 2, 3],          # Hit on 1
            # Fault: Need to replace. Future: 1 doesn't appear, 2 doesn't appear, 3 doesn't appear.
            # All are never used again. Optimal picks the first one found (frame 1 = page 2,
            # but actually let's trace: page 2 never used again, page 3 never used again.
            # The first one never-used-again is page 2 (frame index 1).
        ]
        expected_faults = [True, True, True, False, True]

        for i in range(4):  # First 4 steps are deterministic
            self.assertEqual(result["steps"][i]["frames"], expected_frames[i], f"Step {i}")
            self.assertEqual(result["steps"][i]["fault"], expected_faults[i], f"Step {i} fault")

        # Step 4: page 4 should be loaded, and one of {2, 3} should be evicted
        # (both are never used again). The specific victim depends on implementation
        # (we evict the first never-used-again page found).
        self.assertTrue(result["steps"][4]["fault"])
        self.assertIn(4, result["steps"][4]["frames"])

    def test_no_mutation_of_input(self):
        pages = [1, 2, 3, 4]
        pages_copy = list(pages)
        optimal(pages, 2)
        self.assertEqual(pages, pages_copy)

    def test_optimal_look_ahead(self):
        """Optimal should keep the page that will be used soonest."""
        pages = [1, 2, 3, 4, 1, 2]
        result = optimal(pages, 3)
        assert_result_structure(self, result, "Optimal", pages)
        # Steps:
        #   1 → [1, -, -]  FAULT
        #   2 → [1, 2, -]  FAULT
        #   3 → [1, 2, 3]  FAULT
        #   4 → fault, future=[1,2]. 3 is never used → evict 3
        #        [1, 2, 4]  FAULT
        #   1 → [1, 2, 4]  HIT
        #   2 → [1, 2, 4]  HIT
        self.assertEqual(result["page_faults"], 4)
        self.assertEqual(result["page_hits"], 2)
        self.assertEqual(result["steps"][3]["frames"], [1, 2, 4])


# =======================================================================
# Cross-algorithm comparison tests
# =======================================================================

class TestCompareAlgorithms(unittest.TestCase):
    """Tests that verify cross-algorithm behavior and the compare function."""

    def test_all_three_produce_different_faults(self):
        """Classic example where FIFO, LRU, and Optimal give different fault counts."""
        pages = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
        frames = 3

        r_fifo = fifo(pages, frames)
        r_lru  = lru(pages, frames)
        r_opt  = optimal(pages, frames)

        # These are the well-known textbook values:
        self.assertEqual(r_fifo["page_faults"], 15)
        self.assertEqual(r_lru["page_faults"],  12)
        self.assertEqual(r_opt["page_faults"],   9)

        # Optimal should always be <= the others.
        self.assertLessEqual(r_opt["page_faults"], r_lru["page_faults"])
        self.assertLessEqual(r_opt["page_faults"], r_fifo["page_faults"])

    def test_compare_algorithms_function(self):
        """The compare_algorithms convenience function returns all three."""
        pages = [1, 2, 3, 4, 1, 2]
        results = compare_algorithms(pages, 3)

        self.assertIn("FIFO", results)
        self.assertIn("LRU", results)
        self.assertIn("Optimal", results)

        for alg_name, result in results.items():
            assert_result_structure(self, result, alg_name, pages)

    def test_identical_when_enough_frames(self):
        """When frames >= unique pages, all algorithms have 0 replacements (only initial faults)."""
        pages = [1, 2, 3, 1, 2, 3, 1]
        frames = 3   # Exactly enough for all unique pages

        results = compare_algorithms(pages, frames)

        for alg_name, result in results.items():
            # Only the first 3 accesses should fault.
            self.assertEqual(result["page_faults"], 3, f"{alg_name} should fault only 3 times")
            self.assertEqual(result["page_hits"], 4, f"{alg_name} should hit 4 times")

    def test_invariant_faults_plus_hits(self):
        """For any input, page_faults + page_hits == len(pages) for all algorithms."""
        pages = [5, 4, 3, 2, 1, 5, 4, 3, 2, 1]
        results = compare_algorithms(pages, 3)

        for alg_name, result in results.items():
            self.assertEqual(
                result["page_faults"] + result["page_hits"],
                len(pages),
                f"Invariant violated for {alg_name}"
            )


if __name__ == "__main__":
    unittest.main()
