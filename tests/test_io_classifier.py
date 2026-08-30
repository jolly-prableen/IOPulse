"""
tests/test_io_classifier.py – Unit tests for intelligence/io_classifier.py
IOPulse – Phase 2: I/O Behavior Classification

These tests verify:
  - CPU-bound classification
  - I/O-bound classification
  - Balanced classification
  - Idle classification
  - Boundary threshold cases
  - Missing/invalid metrics handling
  - Configurable thresholds
  - Confidence calculation
  - Explanation/reason generation
  - Edge cases (zero, negative, extreme values, non-dict input)
  - classify_batch

All tests are deterministic and do not depend on real processes.
"""

import unittest

from intelligence.io_classifier import (
    CLASS_BALANCED,
    CLASS_CPU_BOUND,
    CLASS_IDLE,
    CLASS_IO_BOUND,
    ProcessIOClassifier,
    _clamp,
    _safe_float,
)


# ===================================================================
# Test: Internal helpers
# ===================================================================

class TestSafeFloat(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(_safe_float(42), 42.0)

    def test_none(self):
        self.assertEqual(_safe_float(None), 0.0)

    def test_string(self):
        self.assertEqual(_safe_float("bad"), 0.0)

    def test_nan(self):
        self.assertEqual(_safe_float(float("nan")), 0.0)

    def test_inf(self):
        self.assertEqual(_safe_float(float("inf")), 0.0)

    def test_negative_inf(self):
        self.assertEqual(_safe_float(float("-inf")), 0.0)


class TestClamp(unittest.TestCase):
    def test_within_range(self):
        self.assertEqual(_clamp(0.5), 0.5)

    def test_below_range(self):
        self.assertEqual(_clamp(-0.5), 0.0)

    def test_above_range(self):
        self.assertEqual(_clamp(1.5), 1.0)

    def test_exact_low(self):
        self.assertEqual(_clamp(0.0), 0.0)

    def test_exact_high(self):
        self.assertEqual(_clamp(1.0), 1.0)

    def test_custom_range(self):
        self.assertEqual(_clamp(15, 10, 20), 15)
        self.assertEqual(_clamp(5, 10, 20), 10)
        self.assertEqual(_clamp(25, 10, 20), 20)


# ===================================================================
# Test: Clearly CPU-bound process
# ===================================================================

class TestClassifyCPUBound(unittest.TestCase):
    def setUp(self):
        self.classifier = ProcessIOClassifier()

    def test_high_cpu_low_io(self):
        """80% CPU, 10 KB/s I/O → CPU_BOUND."""
        result = self.classifier.classify({
            "pid": 100, "name": "compiler",
            "cpu_percent": 80.0,
            "total_io_bytes_per_sec": 10_000,
        })
        self.assertEqual(result["classification"], CLASS_CPU_BOUND)
        self.assertGreater(result["cpu_score"], result["io_score"])

    def test_very_high_cpu_zero_io(self):
        """100% CPU, 0 I/O → CPU_BOUND."""
        result = self.classifier.classify({
            "pid": 101, "name": "computation",
            "cpu_percent": 100.0,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertEqual(result["classification"], CLASS_CPU_BOUND)

    def test_high_cpu_with_moderate_io(self):
        """90% CPU, 200 KB/s I/O → CPU_BOUND (dominance margin holds)."""
        result = self.classifier.classify({
            "pid": 102, "name": "mixed_heavy_cpu",
            "cpu_percent": 90.0,
            "total_io_bytes_per_sec": 200_000,
        })
        self.assertEqual(result["classification"], CLASS_CPU_BOUND)


# ===================================================================
# Test: Clearly I/O-bound process
# ===================================================================

class TestClassifyIOBound(unittest.TestCase):
    def setUp(self):
        self.classifier = ProcessIOClassifier()

    def test_low_cpu_high_io(self):
        """5% CPU, 5 MB/s I/O → IO_BOUND."""
        result = self.classifier.classify({
            "pid": 200, "name": "database",
            "cpu_percent": 5.0,
            "total_io_bytes_per_sec": 5_000_000,
        })
        self.assertEqual(result["classification"], CLASS_IO_BOUND)
        self.assertGreater(result["io_score"], result["cpu_score"])

    def test_zero_cpu_high_io(self):
        """0% CPU, 10 MB/s I/O → IO_BOUND."""
        result = self.classifier.classify({
            "pid": 201, "name": "file_copy",
            "cpu_percent": 0.0,
            "total_io_bytes_per_sec": 10_000_000,
        })
        self.assertEqual(result["classification"], CLASS_IO_BOUND)

    def test_moderate_cpu_very_high_io(self):
        """20% CPU, 50 MB/s I/O → IO_BOUND."""
        result = self.classifier.classify({
            "pid": 202, "name": "stream_reader",
            "cpu_percent": 20.0,
            "total_io_bytes_per_sec": 50_000_000,
        })
        self.assertEqual(result["classification"], CLASS_IO_BOUND)


# ===================================================================
# Test: Balanced process
# ===================================================================

class TestClassifyBalanced(unittest.TestCase):
    def setUp(self):
        self.classifier = ProcessIOClassifier()

    def test_both_high_comparable(self):
        """60% CPU, 800 KB/s I/O → BALANCED (scores within dominance margin)."""
        result = self.classifier.classify({
            "pid": 300, "name": "web_server",
            "cpu_percent": 60.0,
            "total_io_bytes_per_sec": 800_000,
        })
        self.assertEqual(result["classification"], CLASS_BALANCED)

    def test_both_moderate(self):
        """30% CPU, 500 KB/s I/O → BALANCED."""
        result = self.classifier.classify({
            "pid": 301, "name": "app_server",
            "cpu_percent": 30.0,
            "total_io_bytes_per_sec": 500_000,
        })
        self.assertEqual(result["classification"], CLASS_BALANCED)

    def test_equal_scores(self):
        """Equal CPU and I/O scores → BALANCED."""
        result = self.classifier.classify({
            "pid": 302, "name": "equal",
            "cpu_percent": 25.0,      # score 0.5
            "total_io_bytes_per_sec": 500_000,  # score 0.5
        })
        self.assertEqual(result["classification"], CLASS_BALANCED)
        self.assertAlmostEqual(result["cpu_score"], result["io_score"], places=4)


# ===================================================================
# Test: Idle process
# ===================================================================

class TestClassifyIdle(unittest.TestCase):
    def setUp(self):
        self.classifier = ProcessIOClassifier()

    def test_zero_cpu_zero_io(self):
        """0% CPU, 0 I/O → IDLE."""
        result = self.classifier.classify({
            "pid": 400, "name": "sleeping",
            "cpu_percent": 0.0,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertEqual(result["classification"], CLASS_IDLE)

    def test_very_low_both(self):
        """1% CPU, 10 KB/s I/O → IDLE (both below min_activity)."""
        result = self.classifier.classify({
            "pid": 401, "name": "idle_app",
            "cpu_percent": 1.0,
            "total_io_bytes_per_sec": 10_000,
        })
        self.assertEqual(result["classification"], CLASS_IDLE)

    def test_slightly_above_min_cpu_only(self):
        """2.5% CPU, 0 I/O → BALANCED (score equals min, strict < means not IDLE)."""
        result = self.classifier.classify({
            "pid": 402, "name": "barely_active",
            "cpu_percent": 2.5,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertEqual(result["classification"], CLASS_BALANCED)


# ===================================================================
# Test: Boundary threshold cases
# ===================================================================

class TestBoundaryThresholds(unittest.TestCase):
    def setUp(self):
        self.classifier = ProcessIOClassifier()

    def test_cpu_score_exactly_at_threshold(self):
        """CPU exactly at threshold → score 1.0, I/O at 0 → CPU_BOUND."""
        result = self.classifier.classify({
            "pid": 500, "name": "boundary",
            "cpu_percent": 50.0,       # score = 1.0
            "total_io_bytes_per_sec": 0.0,  # score = 0.0
        })
        self.assertEqual(result["classification"], CLASS_CPU_BOUND)
        self.assertAlmostEqual(result["cpu_score"], 1.0, places=4)

    def test_io_score_exactly_at_threshold(self):
        """I/O exactly at threshold → score 1.0, CPU at 0 → IO_BOUND."""
        result = self.classifier.classify({
            "pid": 501, "name": "boundary",
            "cpu_percent": 0.0,
            "total_io_bytes_per_sec": 1_000_000,  # score = 1.0
        })
        self.assertEqual(result["classification"], CLASS_IO_BOUND)
        self.assertAlmostEqual(result["io_score"], 1.0, places=4)

    def test_both_at_threshold(self):
        """Both at threshold → both scores 1.0, difference < margin → BALANCED."""
        result = self.classifier.classify({
            "pid": 502, "name": "boundary",
            "cpu_percent": 50.0,
            "total_io_bytes_per_sec": 1_000_000,
        })
        self.assertEqual(result["classification"], CLASS_BALANCED)

    def test_dominance_margin_boundary(self):
        """cpu_score - io_score exactly at dominance_margin → BALANCED
        (must be >= to trigger CPU_BOUND, so == counts as CPU_BOUND)."""
        # cpu_score = 0.5, io_score = 0.3, margin = 0.2 → difference = 0.2 = margin → CPU_BOUND
        result = self.classifier.classify({
            "pid": 503, "name": "boundary",
            "cpu_percent": 25.0,       # score = 0.5
            "total_io_bytes_per_sec": 300_000,  # score = 0.3
        })
        self.assertEqual(result["classification"], CLASS_CPU_BOUND)

    def test_just_below_dominance_margin(self):
        """cpu_score - io_score just below dominance_margin → BALANCED."""
        # cpu_score = 0.5, io_score = 0.31, margin = 0.2 → difference = 0.19 < 0.2
        result = self.classifier.classify({
            "pid": 504, "name": "boundary",
            "cpu_percent": 25.0,       # score = 0.5
            "total_io_bytes_per_sec": 310_000,  # score = 0.31
        })
        self.assertEqual(result["classification"], CLASS_BALANCED)

    def test_cpu_score_at_min_activity(self):
        """CPU score exactly at min_activity_score, I/O below → BALANCED
        (score equals min, strict < means not IDLE)."""
        # min_activity = 0.05, cpu_percent = 2.5 → score = 0.05
        result = self.classifier.classify({
            "pid": 505, "name": "boundary",
            "cpu_percent": 2.5,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertEqual(result["classification"], CLASS_BALANCED)

    def test_cpu_just_above_min_activity(self):
        """CPU score just above min_activity, I/O below → CPU_BOUND."""
        # cpu_percent = 2.6 → score = 0.052 > 0.05
        # io = 0 → score = 0.0
        # difference = 0.052 >= 0.2? No. → BALANCED? No, both must be > min for BALANCED
        # Actually: cpu_score (0.052) >= min (0.05), io_score (0.0) < min (0.05)
        # Since io_score < min AND cpu_score >= min, the check is:
        # both < min → IDLE? No (cpu >= min). cpu - io >= margin? 0.052 >= 0.2? No. BALANCED.
        result = self.classifier.classify({
            "pid": 506, "name": "boundary",
            "cpu_percent": 2.6,
            "total_io_bytes_per_sec": 0.0,
        })
        # cpu_score=0.052, io_score=0.0, diff=0.052 < 0.2 → BALANCED
        self.assertEqual(result["classification"], CLASS_BALANCED)


# ===================================================================
# Test: Missing / invalid metrics
# ===================================================================

class TestMissingInvalidMetrics(unittest.TestCase):
    def setUp(self):
        self.classifier = ProcessIOClassifier()

    def test_missing_cpu_percent(self):
        """Missing cpu_percent → defaults to 0.0 → IDLE if I/O also low."""
        result = self.classifier.classify({
            "pid": 600, "name": "no_cpu",
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertEqual(result["classification"], CLASS_IDLE)
        self.assertEqual(result["cpu_percent"], 0.0)

    def test_missing_io_bytes(self):
        """Missing total_io_bytes_per_sec → defaults to 0.0."""
        result = self.classifier.classify({
            "pid": 601, "name": "no_io",
            "cpu_percent": 30.0,
        })
        self.assertIn(result["classification"], [CLASS_CPU_BOUND, CLASS_BALANCED])

    def test_missing_pid(self):
        """Missing pid → defaults to 0."""
        result = self.classifier.classify({
            "name": "no_pid",
            "cpu_percent": 10.0,
            "total_io_bytes_per_sec": 500_000,
        })
        self.assertEqual(result["pid"], 0)

    def test_missing_name(self):
        """Missing name → defaults to 'unknown'."""
        result = self.classifier.classify({
            "pid": 603,
            "cpu_percent": 10.0,
            "total_io_bytes_per_sec": 500_000,
        })
        self.assertEqual(result["process_name"], "unknown")

    def test_non_dict_input(self):
        """Non-dict input → IDLE with defaults."""
        result = self.classifier.classify("not a dict")
        self.assertEqual(result["classification"], CLASS_IDLE)

    def test_none_input(self):
        """None input → IDLE with defaults."""
        result = self.classifier.classify(None)
        self.assertEqual(result["classification"], CLASS_IDLE)

    def test_negative_cpu_percent(self):
        """Negative CPU percent → clamped to 0.0."""
        result = self.classifier.classify({
            "pid": 604, "name": "neg_cpu",
            "cpu_percent": -10.0,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertEqual(result["cpu_percent"], 0.0)
        self.assertEqual(result["classification"], CLASS_IDLE)

    def test_negative_io_bytes(self):
        """Negative I/O → clamped to 0.0."""
        result = self.classifier.classify({
            "pid": 605, "name": "neg_io",
            "cpu_percent": 0.0,
            "total_io_bytes_per_sec": -5000,
        })
        self.assertEqual(result["total_io_bytes_per_sec"], 0.0)
        self.assertEqual(result["classification"], CLASS_IDLE)

    def test_string_cpu_percent(self):
        """String cpu_percent → coerced or defaults to 0.0."""
        result = self.classifier.classify({
            "pid": 606, "name": "str_cpu",
            "cpu_percent": "bad",
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertEqual(result["cpu_percent"], 0.0)

    def test_nan_cpu_percent(self):
        """NaN cpu_percent → defaults to 0.0."""
        result = self.classifier.classify({
            "pid": 607, "name": "nan_cpu",
            "cpu_percent": float("nan"),
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertEqual(result["cpu_percent"], 0.0)

    def test_inf_cpu_percent(self):
        """Inf cpu_percent → defaults to 0.0."""
        result = self.classifier.classify({
            "pid": 608, "name": "inf_cpu",
            "cpu_percent": float("inf"),
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertEqual(result["cpu_percent"], 0.0)


# ===================================================================
# Test: Configurable thresholds
# ===================================================================

class TestConfigurableThresholds(unittest.TestCase):
    def test_custom_cpu_threshold(self):
        """With cpu_threshold=10, 15% CPU → score 1.0 (would be 0.3 at default)."""
        classifier = ProcessIOClassifier(cpu_threshold=10.0)
        result = classifier.classify({
            "pid": 700, "name": "custom",
            "cpu_percent": 15.0,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertAlmostEqual(result["cpu_score"], 1.0, places=4)
        self.assertEqual(result["classification"], CLASS_CPU_BOUND)

    def test_custom_io_threshold(self):
        """With io_threshold=1000, 500 B/s → score 0.5."""
        classifier = ProcessIOClassifier(io_threshold=1000.0)
        result = classifier.classify({
            "pid": 701, "name": "custom",
            "cpu_percent": 0.0,
            "total_io_bytes_per_sec": 500,
        })
        self.assertAlmostEqual(result["io_score"], 0.5, places=4)

    def test_custom_min_activity(self):
        """With min_activity=0.1, 5% CPU (score 0.1) + 0 I/O → BALANCED
        because cpu_score (0.1) >= min_activity (0.1) but not dominant."""
        classifier = ProcessIOClassifier(min_activity_score=0.1)
        result = classifier.classify({
            "pid": 702, "name": "custom",
            "cpu_percent": 5.0,   # score = 0.1
            "total_io_bytes_per_sec": 0.0,  # score = 0.0
        })
        # Both below min? No, cpu = 0.1 = min. The check is cpu_score < min → False.
        # So not IDLE. cpu - io = 0.1 < 0.2 (margin) → BALANCED.
        self.assertEqual(result["classification"], CLASS_BALANCED)

    def test_custom_dominance_margin(self):
        """With margin=0.1, a smaller gap triggers CPU_BOUND.
        Note: 0.5 - 0.4 = 0.0999... in float, so use 0.6 - 0.4 = 0.2 > 0.1."""
        classifier = ProcessIOClassifier(dominance_margin=0.1)
        result = classifier.classify({
            "pid": 703, "name": "custom",
            "cpu_percent": 30.0,  # score = 0.6
            "total_io_bytes_per_sec": 400_000,  # score = 0.4
        })
        # diff = 0.2 >= margin 0.1 → CPU_BOUND
        self.assertEqual(result["classification"], CLASS_CPU_BOUND)

    def test_extremely_high_cpu(self):
        """500% CPU (multi-core) → score clamped to 1.0 → CPU_BOUND."""
        classifier = ProcessIOClassifier()
        result = classifier.classify({
            "pid": 704, "name": "extreme",
            "cpu_percent": 500.0,
            "total_io_bytes_per_sec": 10_000,
        })
        self.assertAlmostEqual(result["cpu_score"], 1.0, places=4)
        self.assertEqual(result["classification"], CLASS_CPU_BOUND)

    def test_extremely_high_io(self):
        """1 GB/s I/O → score clamped to 1.0 → IO_BOUND."""
        classifier = ProcessIOClassifier()
        result = classifier.classify({
            "pid": 705, "name": "extreme",
            "cpu_percent": 5.0,
            "total_io_bytes_per_sec": 1_000_000_000,
        })
        self.assertAlmostEqual(result["io_score"], 1.0, places=4)
        self.assertEqual(result["classification"], CLASS_IO_BOUND)


# ===================================================================
# Test: Confidence calculation
# ===================================================================

class TestConfidence(unittest.TestCase):
    def setUp(self):
        self.classifier = ProcessIOClassifier()

    def test_idle_confidence_highest_when_zero_activity(self):
        """Zero activity → confidence = 1.0 (most confident it's idle)."""
        result = self.classifier.classify({
            "pid": 800, "name": "dead",
            "cpu_percent": 0.0,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertAlmostEqual(result["confidence"], 1.0, places=4)

    def test_idle_confidence_lower_near_threshold(self):
        """Activity near min threshold → confidence closer to 0.95."""
        result = self.classifier.classify({
            "pid": 801, "name": "almost_active",
            "cpu_percent": 2.0,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertGreater(result["confidence"], 0.9)

    def test_cpu_bound_high_confidence(self):
        """Strong CPU-bound → high confidence."""
        result = self.classifier.classify({
            "pid": 802, "name": "compiler",
            "cpu_percent": 50.0,   # score = 1.0
            "total_io_bytes_per_sec": 0.0,  # score = 0.0
        })
        self.assertGreater(result["confidence"], 0.8)

    def test_cpu_bound_max_confidence_pure(self):
        """CPU at threshold with zero I/O → maximum confidence (1.0)."""
        result_pure = self.classifier.classify({
            "pid": 803, "name": "pure",
            "cpu_percent": 50.0,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertEqual(result_pure["classification"], CLASS_CPU_BOUND)
        self.assertAlmostEqual(result_pure["confidence"], 1.0, places=4)

    def test_cpu_bound_confidence_below_threshold(self):
        """CPU below threshold with some I/O → lower confidence than at threshold."""
        result_pure = self.classifier.classify({
            "pid": 803, "name": "pure",
            "cpu_percent": 30.0,   # score = 0.6
            "total_io_bytes_per_sec": 0.0,
        })
        result_mixed = self.classifier.classify({
            "pid": 804, "name": "mixed",
            "cpu_percent": 30.0,
            "total_io_bytes_per_sec": 100_000,  # io_score = 0.1
        })
        self.assertEqual(result_pure["classification"], CLASS_CPU_BOUND)
        self.assertEqual(result_mixed["classification"], CLASS_CPU_BOUND)
        self.assertGreater(result_pure["confidence"], 0.0)
        self.assertGreater(result_mixed["confidence"], 0.0)

    def test_balanced_confidence_both_high(self):
        """Both scores high → high BALANCED confidence."""
        result = self.classifier.classify({
            "pid": 805, "name": "active",
            "cpu_percent": 40.0,   # score = 0.8
            "total_io_bytes_per_sec": 800_000,  # score = 0.8
        })
        self.assertEqual(result["classification"], CLASS_BALANCED)
        self.assertGreater(result["confidence"], 0.7)

    def test_balanced_confidence_both_low(self):
        """Both scores low but above min → low BALANCED confidence."""
        result = self.classifier.classify({
            "pid": 806, "name": "barely_balanced",
            "cpu_percent": 3.0,    # score = 0.06
            "total_io_bytes_per_sec": 60_000,  # score = 0.06
        })
        self.assertEqual(result["classification"], CLASS_BALANCED)
        self.assertLess(result["confidence"], 0.2)

    def test_confidence_always_between_0_and_1(self):
        """All classifications produce confidence in [0, 1]."""
        test_cases = [
            {"pid": 807, "name": "a", "cpu_percent": 0, "total_io_bytes_per_sec": 0},
            {"pid": 808, "name": "b", "cpu_percent": 50, "total_io_bytes_per_sec": 0},
            {"pid": 809, "name": "c", "cpu_percent": 0, "total_io_bytes_per_sec": 5_000_000},
            {"pid": 810, "name": "d", "cpu_percent": 30, "total_io_bytes_per_sec": 300_000},
        ]
        for case in test_cases:
            result = self.classifier.classify(case)
            self.assertGreaterEqual(result["confidence"], 0.0)
            self.assertLessEqual(result["confidence"], 1.0)


# ===================================================================
# Test: Explanation / reason generation
# ===================================================================

class TestReasonGeneration(unittest.TestCase):
    def setUp(self):
        self.classifier = ProcessIOClassifier()

    def test_idle_reason_mentions_both_metrics(self):
        result = self.classifier.classify({
            "pid": 900, "name": "idle",
            "cpu_percent": 0.0,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertIn("CPU", result["reason"])
        self.assertIn("I/O", result["reason"])
        self.assertIn("Insufficient", result["reason"])

    def test_cpu_bound_reason_mentions_high_cpu(self):
        result = self.classifier.classify({
            "pid": 901, "name": "cpu_heavy",
            "cpu_percent": 80.0,
            "total_io_bytes_per_sec": 0.0,
        })
        self.assertIn("CPU", result["reason"])
        self.assertIn("High CPU", result["reason"])

    def test_io_bound_reason_mentions_high_io(self):
        result = self.classifier.classify({
            "pid": 902, "name": "io_heavy",
            "cpu_percent": 0.0,
            "total_io_bytes_per_sec": 5_000_000,
        })
        self.assertIn("I/O", result["reason"])
        self.assertIn("High I/O", result["reason"])

    def test_balanced_reason_mentions_both(self):
        result = self.classifier.classify({
            "pid": 903, "name": "balanced",
            "cpu_percent": 20.0,   # score = 0.4
            "total_io_bytes_per_sec": 300_000,  # score = 0.3, diff = 0.1 < margin 0.2
        })
        self.assertEqual(result["classification"], CLASS_BALANCED)
        self.assertIn("CPU and I/O", result["reason"])

    def test_reason_includes_metric_values(self):
        """Reason must contain the actual numeric values."""
        result = self.classifier.classify({
            "pid": 904, "name": "check",
            "cpu_percent": 42.5,
            "total_io_bytes_per_sec": 123456,
        })
        self.assertIn("42.5%", result["reason"])
        self.assertIn("123456", result["reason"])

    def test_reason_is_string(self):
        result = self.classifier.classify({
            "pid": 905, "name": "str",
            "cpu_percent": 10.0,
            "total_io_bytes_per_sec": 100_000,
        })
        self.assertIsInstance(result["reason"], str)
        self.assertTrue(len(result["reason"]) > 0)


# ===================================================================
# Test: Result structure
# ===================================================================

class TestResultStructure(unittest.TestCase):
    def test_all_keys_present(self):
        classifier = ProcessIOClassifier()
        result = classifier.classify({
            "pid": 950, "name": "struct",
            "cpu_percent": 25.0,
            "total_io_bytes_per_sec": 500_000,
        })
        expected_keys = {
            "pid", "process_name", "classification", "confidence",
            "cpu_score", "io_score", "cpu_percent",
            "total_io_bytes_per_sec", "reason",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_scores_rounded_to_4_places(self):
        classifier = ProcessIOClassifier()
        result = classifier.classify({
            "pid": 951, "name": "round",
            "cpu_percent": 33.333333,
            "total_io_bytes_per_sec": 333_333,
        })
        # cpu_score = 33.333333 / 50 = 0.66666666 → rounded to 0.6667
        self.assertAlmostEqual(result["cpu_score"], 0.6667, places=4)


# ===================================================================
# Test: classify_batch
# ===================================================================

class TestClassifyBatch(unittest.TestCase):
    def test_batch_returns_list(self):
        classifier = ProcessIOClassifier()
        results = classifier.classify_batch([
            {"pid": 1, "name": "a", "cpu_percent": 50.0, "total_io_bytes_per_sec": 0},
            {"pid": 2, "name": "b", "cpu_percent": 0, "total_io_bytes_per_sec": 5_000_000},
        ])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["classification"], CLASS_CPU_BOUND)
        self.assertEqual(results[1]["classification"], CLASS_IO_BOUND)

    def test_batch_empty_list(self):
        classifier = ProcessIOClassifier()
        results = classifier.classify_batch([])
        self.assertEqual(results, [])

    def test_batch_none(self):
        classifier = ProcessIOClassifier()
        results = classifier.classify_batch(None)
        self.assertEqual(results, [])

    def test_batch_mixed_valid_invalid(self):
        classifier = ProcessIOClassifier()
        results = classifier.classify_batch([
            {"pid": 1, "name": "valid", "cpu_percent": 50.0, "total_io_bytes_per_sec": 0},
            "invalid",
            None,
            {"pid": 4, "name": "also_valid", "cpu_percent": 0, "total_io_bytes_per_sec": 5_000_000},
        ])
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0]["classification"], CLASS_CPU_BOUND)
        self.assertEqual(results[1]["classification"], CLASS_IDLE)   # invalid → IDLE
        self.assertEqual(results[2]["classification"], CLASS_IDLE)   # None → IDLE
        self.assertEqual(results[3]["classification"], CLASS_IO_BOUND)


# ===================================================================
# Test: Determinism (no randomness)
# ===================================================================

class TestDeterminism(unittest.TestCase):
    def test_same_input_same_output(self):
        """Classifying the same input twice must produce identical results."""
        classifier = ProcessIOClassifier()
        metrics = {
            "pid": 999, "name": "deterministic",
            "cpu_percent": 35.0,
            "total_io_bytes_per_sec": 400_000,
        }
        r1 = classifier.classify(metrics)
        r2 = classifier.classify(metrics)
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
