"""Process I/O behavior classification for IOPulse.

This module classifies observed processes into one of four categories
based on their CPU utilization and disk I/O behavior:

  - CPU_BOUND   – high CPU activity, low relative I/O
  - IO_BOUND    – high I/O activity, low relative CPU
  - BALANCED    – both CPU and I/O are significant
  - IDLE        – both CPU and I/O below minimum activity thresholds

=== DESIGN ===
Classification uses a transparent, rule-based scoring system.  Each
process receives a CPU score and an I/O score, both normalized to [0, 1]
by configurable thresholds.  The classifier then compares these scores
against configurable minimum-activity and dominance thresholds.

Every classification includes a deterministic confidence value and a
human-readable explanation derived directly from the observed metrics.
No machine learning is used.

The classifier is intentionally decoupled from psutil: it accepts plain
metric dictionaries (as produced by ``intelligence.io_metrics``) and
returns plain result dictionaries.  This makes it straightforward to
test without real processes and easy to consume from the dashboard.
"""

from __future__ import annotations

from math import isinf, isnan
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Default thresholds – all configurable via ProcessIOClassifier constructor
# ---------------------------------------------------------------------------

# CPU score = clamp(cpu_percent / cpu_threshold, 0, 1)
# A process at exactly this threshold gets a CPU score of 1.0.
CPU_SCORE_THRESHOLD: float = 50.0

# I/O score = clamp(total_io_bytes_per_sec / io_threshold, 0, 1)
# A process at exactly this threshold gets an I/O score of 1.0.
IO_SCORE_THRESHOLD: float = 1_000_000.0  # 1 MB/s

# Minimum score required for a dimension to count as "active".
# Below this on both dimensions → IDLE.
MIN_ACTIVITY_SCORE: float = 0.05

# How much the dominant score must exceed the other to pick a winner.
# If |cpu_score - io_score| < dominance_margin → BALANCED.
DOMINANCE_MARGIN: float = 0.20

# Classification labels
CLASS_CPU_BOUND: str = "CPU_BOUND"
CLASS_IO_BOUND: str = "IO_BOUND"
CLASS_BALANCED: str = "BALANCED"
CLASS_IDLE: str = "IDLE"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any, default: float = 0.0) -> float:
    """Return value as float or default when the input is invalid."""
    if value is None:
        return default

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default

    if isnan(numeric) or isinf(numeric):
        return default

    return numeric


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp value to [low, high]."""
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class ProcessIOClassifier:
    """Classify processes as CPU-bound, I/O-bound, balanced, or idle.

    The classifier uses a scoring system with configurable thresholds:

        cpu_score = clamp(cpu_percent / cpu_threshold, 0, 1)
        io_score  = clamp(total_io_bytes_per_sec / io_threshold, 0, 1)

    Classification rules (evaluated in order):

        1. If both scores < min_activity_score → IDLE
        2. If cpu_score - io_score >= dominance_margin → CPU_BOUND
        3. If io_score - cpu_score >= dominance_margin → IO_BOUND
        4. Otherwise → BALANCED

    All thresholds are configurable at construction time.
    """

    def __init__(
        self,
        cpu_threshold: float = CPU_SCORE_THRESHOLD,
        io_threshold: float = IO_SCORE_THRESHOLD,
        min_activity_score: float = MIN_ACTIVITY_SCORE,
        dominance_margin: float = DOMINANCE_MARGIN,
    ) -> None:
        """Initialise the classifier with configurable thresholds.

        Args:
            cpu_threshold: CPU percent that maps to a score of 1.0.
                Default 50.0 means 50% CPU → score 1.0.
            io_threshold: I/O bytes/sec that maps to a score of 1.0.
                Default 1_000_000 (1 MB/s) → score 1.0.
            min_activity_score: Minimum score on either dimension to
                avoid being classified as IDLE.  Default 0.05.
            dominance_margin: How far the dominant score must exceed the
                other to pick CPU_BOUND or IO_BOUND over BALANCED.
                Default 0.20.
        """
        self.cpu_threshold = max(0.001, float(cpu_threshold))
        self.io_threshold = max(0.001, float(io_threshold))
        self.min_activity_score = max(0.0, float(min_activity_score))
        self.dominance_margin = max(0.0, float(dominance_margin))

    def _compute_scores(
        self, cpu_percent: float, total_io_bytes_per_sec: float
    ) -> tuple[float, float]:
        """Compute normalized CPU and I/O scores in [0, 1].

        Negative inputs are clamped to 0.  Values exceeding their
        threshold are capped at 1.0.
        """
        cpu_score = _clamp(cpu_percent / self.cpu_threshold)
        io_score = _clamp(total_io_bytes_per_sec / self.io_threshold)
        return (cpu_score, io_score)

    def _compute_confidence(
        self,
        classification: str,
        cpu_score: float,
        io_score: float,
    ) -> float:
        """Compute a deterministic confidence value in [0, 1].

        The confidence reflects how clearly the metrics support the
        chosen classification:

        - CPU_BOUND / IO_BOUND:
            confidence = min_score + dominance_margin * (1 - dominance_margin)
            where min_score is the lesser of the two scores.  This
            rewards high scores in the dominant dimension while
            penalising when the non-dominant dimension is also active.

        - BALANCED:
            confidence = average of both scores.  Two high, comparable
            scores yield high confidence.

        - IDLE:
            confidence = 1 - max(cpu_score, io_score).  The less
            activity observed, the more confident we are that the
            process is truly idle.
        """
        if classification == CLASS_IDLE:
            return round(1.0 - max(cpu_score, io_score), 4)

        if classification in (CLASS_CPU_BOUND, CLASS_IO_BOUND):
            dominant = max(cpu_score, io_score)
            minor = min(cpu_score, io_score)
            # How far the dominant score extends beyond the minor,
            # scaled by how high the dominant score is overall.
            spread = dominant - minor
            return round(minor + spread * dominant, 4)

        # BALANCED
        return round((cpu_score + io_score) / 2.0, 4)

    def _generate_reason(
        self,
        classification: str,
        cpu_percent: float,
        total_io_bytes_per_sec: float,
        cpu_score: float,
        io_score: float,
    ) -> str:
        """Generate a human-readable explanation for the classification.

        The explanation references actual metric values so the user can
        verify the reasoning.
        """
        if classification == CLASS_IDLE:
            return (
                f"Insufficient activity to classify as CPU- or I/O-bound "
                f"(CPU: {cpu_percent:.1f}%, I/O: {total_io_bytes_per_sec:.0f} B/s)"
            )

        if classification == CLASS_CPU_BOUND:
            return (
                f"High CPU activity with minimal I/O "
                f"(CPU: {cpu_percent:.1f}%, I/O: {total_io_bytes_per_sec:.0f} B/s)"
            )

        if classification == CLASS_IO_BOUND:
            return (
                f"High I/O throughput relative to CPU utilization "
                f"(CPU: {cpu_percent:.1f}%, I/O: {total_io_bytes_per_sec:.0f} B/s)"
            )

        # BALANCED
        return (
            f"CPU and I/O activity are both significant "
            f"(CPU: {cpu_percent:.1f}%, I/O: {total_io_bytes_per_sec:.0f} B/s)"
        )

    def classify(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Classify a single process based on its observed I/O metrics.

        Args:
            metrics: A dictionary as produced by
                ``ProcessIOCollector.collect_single()`` or
                ``ProcessIOCollector.collect_all()``.  The following
                keys are used:

                  - pid                   (required)
                  - name                  (required)
                  - cpu_percent           (used for CPU score)
                  - total_io_bytes_per_sec (used for I/O score)

                Missing or invalid values default to 0.0.

        Returns:
            A classification result dictionary:

                {
                    "pid": int,
                    "process_name": str,
                    "classification": str,    # CPU_BOUND | IO_BOUND | BALANCED | IDLE
                    "confidence": float,      # 0.0 – 1.0
                    "cpu_score": float,       # 0.0 – 1.0
                    "io_score": float,        # 0.0 – 1.0
                    "cpu_percent": float,     # original metric
                    "total_io_bytes_per_sec": float,  # original metric
                    "reason": str,
                }
        """
        if not isinstance(metrics, dict):
            return self._build_result(
                pid=0,
                name="unknown",
                classification=CLASS_IDLE,
                cpu_percent=0.0,
                total_io=0.0,
                cpu_score=0.0,
                io_score=0.0,
            )

        try:
            pid = int(metrics.get("pid", 0))
        except (TypeError, ValueError):
            pid = 0

        name = str(metrics.get("name", "unknown") or "unknown").strip() or "unknown"

        cpu_percent = _safe_float(metrics.get("cpu_percent"), 0.0)
        total_io = _safe_float(metrics.get("total_io_bytes_per_sec"), 0.0)

        # Clamp negatives to zero – negative CPU or I/O is meaningless.
        cpu_percent = max(0.0, cpu_percent)
        total_io = max(0.0, total_io)

        cpu_score, io_score = self._compute_scores(cpu_percent, total_io)

        # Classification rule chain.
        if cpu_score < self.min_activity_score and io_score < self.min_activity_score:
            classification = CLASS_IDLE
        elif (cpu_score - io_score) >= self.dominance_margin:
            classification = CLASS_CPU_BOUND
        elif (io_score - cpu_score) >= self.dominance_margin:
            classification = CLASS_IO_BOUND
        else:
            classification = CLASS_BALANCED

        confidence = self._compute_confidence(classification, cpu_score, io_score)
        reason = self._generate_reason(
            classification, cpu_percent, total_io, cpu_score, io_score
        )

        return self._build_result(
            pid=pid,
            name=name,
            classification=classification,
            cpu_percent=cpu_percent,
            total_io=total_io,
            cpu_score=cpu_score,
            io_score=io_score,
            confidence=confidence,
            reason=reason,
        )

    def classify_batch(
        self, metrics_list: list[Dict[str, Any]]
    ) -> list[Dict[str, Any]]:
        """Classify a batch of process metrics.

        Args:
            metrics_list: List of metrics dicts.

        Returns:
            List of classification results, one per input.  Invalid
            entries receive an IDLE classification with zero scores.
        """
        return [self.classify(m) for m in (metrics_list or [])]

    def _build_result(
        self,
        pid: int,
        name: str,
        classification: str,
        cpu_percent: float,
        total_io: float,
        cpu_score: float,
        io_score: float,
        confidence: float = 0.0,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Construct the standard result dictionary."""
        if not reason:
            reason = self._generate_reason(
                classification, cpu_percent, total_io, cpu_score, io_score
            )
        if confidence == 0.0 and classification != CLASS_IDLE:
            confidence = self._compute_confidence(
                classification, cpu_score, io_score
            )

        return {
            "pid": pid,
            "process_name": name,
            "classification": classification,
            "confidence": round(confidence, 4),
            "cpu_score": round(cpu_score, 4),
            "io_score": round(io_score, 4),
            "cpu_percent": round(cpu_percent, 2),
            "total_io_bytes_per_sec": round(total_io, 2),
            "reason": reason,
        }
