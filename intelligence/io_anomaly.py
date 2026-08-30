"""Process I/O anomaly detection for IOPulse.

This module detects anomalous I/O behavior in observed processes using
explainable, rule-based heuristics.  No machine learning is used — every
detection includes a human-readable explanation.

=== OS CONCEPTS ===

Operating systems track per-process disk I/O.  Several anomaly patterns
can indicate problems:

1. **I/O Spike**
   A sudden, large increase in I/O throughput compared to the process's
   recent history.  May indicate a runaway process, a batch job kicking
   off, or an application bug causing excessive I/O.

2. **I/O Stall**
   A process that was actively performing I/O suddenly goes silent.
   May indicate a hung process, a blocked file lock, or a deadlock
   involving I/O resources.

3. **Sustained High I/O**
   A process maintains extremely high I/O throughput over many
   consecutive observations.  Similar to CPU runaway detection — the
   process may be monopolising disk bandwidth and starving other
   processes.

4. **Read/Write Ratio Shift**
   A process whose read/write ratio changes dramatically from its
   historical baseline.  May indicate a change in workload character
   (e.g., a database switching from read-heavy to write-heavy).

=== DESIGN ===

All detectors accept plain metric dictionaries (as produced by
``intelligence.io_metrics.ProcessIOCollector``) and return plain result
dictionaries.  This keeps the module fully decoupled from psutil and
easy to test with mock data.

Severity levels follow the existing convention:
    "none"     – No anomaly detected.
    "low"      – Early warning signs present.
    "medium"   – Anomaly pattern is forming.
    "high"     – Strong anomaly pattern detected.
    "critical" – Anomaly pattern is very strong; immediate attention needed.
"""

from __future__ import annotations

from math import isinf, isnan
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Default thresholds — all configurable per-detector
# ---------------------------------------------------------------------------

# I/O Spike
SPIKE_MULTIPLIER: float = 5.0
SPIKE_MIN_HISTORY: int = 3
SPIKE_MIN_RATE: float = 10_000.0  # 10 KB/s minimum to consider a spike

# I/O Stall
STALL_MIN_PREVIOUS_RATE: float = 50_000.0  # 50 KB/s — process must have been active
STALL_CONSECUTIVE_ZERO: int = 3
STALL_ZERO_THRESHOLD: float = 100.0  # below 100 B/s counts as "zero"

# Sustained High I/O
SUSTAINED_HIGH_RATE: float = 5_000_000.0  # 5 MB/s
SUSTAINED_CONSECUTIVE: int = 5

# Read/Write Ratio Shift
RATIO_SHIFT_MIN_RATIO: float = 0.1  # ignore near-zero ratios
RATIO_SHIFT_MULTIPLIER: float = 5.0  # new ratio must be N× the old
RATIO_SHIFT_MIN_HISTORY: int = 5


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


def _safe_rate(entry: Any, key: str = "total_io_bytes_per_sec") -> float:
    """Safely extract a rate value from a dict-like entry.

    Handles None, non-dict entries, and missing keys gracefully.
    """
    if not isinstance(entry, dict):
        return 0.0
    return _safe_float(entry.get(key), 0.0)


def _safe_ratio(entry: Any) -> float:
    """Safely extract a read/write ratio, treating inf as 1e6.

    Infinite ratios occur when a process reads but does not write (or
    vice versa).  We clamp to a large sentinel for comparison purposes.
    """
    if not isinstance(entry, dict):
        return 0.0
    raw = entry.get("read_write_ratio")
    if raw is None:
        return 0.0
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if isnan(val):
        return 0.0
    if isinf(val):
        return 1e6
    return val


# ===================================================================
# I/O SPIKE DETECTION
# ===================================================================

def detect_io_spike(
    history: List[Dict[str, Any]],
    spike_multiplier: float = SPIKE_MULTIPLIER,
    min_history: int = SPIKE_MIN_HISTORY,
    min_rate: float = SPIKE_MIN_RATE,
) -> Dict[str, Any]:
    """Detect a sudden spike in I/O throughput.

    === ALGORITHM ===
    1. Compute the average I/O rate over the last ``min_history``
       observations (excluding the most recent one).
    2. Compare the most recent observation's rate to this baseline.
    3. If the ratio exceeds ``spike_multiplier``, flag an I/O spike.

    The idea: a normal process has relatively stable I/O.  A sudden
    jump of 5× (or more) above its own recent average is anomalous.

    Parameters:
        history           – List of I/O metrics dicts (each must contain
                            ``total_io_bytes_per_sec``).  Ordered oldest
                            to newest.
        spike_multiplier  – How many times above the baseline average
                            triggers a spike.  Default: 5.0.
        min_history       – Minimum observations required (must have at
                            least this many BEFORE the latest sample).
                            Default: 3.
        min_rate          – Minimum baseline rate (B/s) for spike
                            detection to activate.  Prevents false
                            positives on nearly-idle processes.
                            Default: 10,000 (10 KB/s).

    Returns:
        {
            "anomaly":          bool,
            "type":             "io_spike" | "none",
            "severity":         str,
            "reason":           str,
            "current_rate":     float,
            "baseline_rate":    float,
            "ratio":            float,
            "num_observations": int,
            "thresholds":       {
                "spike_multiplier": float,
                "min_rate":         float,
            },
        }
    """
    if not isinstance(history, list) or len(history) < min_history + 1:
        return {
            "anomaly": False,
            "type": "none",
            "severity": "none",
            "reason": (
                f"Insufficient history for I/O spike detection "
                f"(need {min_history + 1}, got {len(history) if isinstance(history, list) else 0})."
            ),
            "current_rate": 0.0,
            "baseline_rate": 0.0,
            "ratio": 0.0,
            "num_observations": len(history) if isinstance(history, list) else 0,
            "thresholds": {
                "spike_multiplier": spike_multiplier,
                "min_rate": min_rate,
            },
        }

    current_rate = _safe_rate(history[-1])

    # Baseline = average of all but the last observation.
    baseline_samples = history[:-1]
    rates = [_safe_rate(h) for h in baseline_samples]
    baseline_rate = sum(rates) / len(rates) if rates else 0.0

    ratio = (current_rate / baseline_rate) if baseline_rate > 0 else 0.0

    anomaly = False
    severity = "none"
    reason = "I/O rate is within normal range relative to recent history."

    if baseline_rate >= min_rate and ratio >= spike_multiplier:
        anomaly = True
        if ratio >= spike_multiplier * 3:
            severity = "critical"
        elif ratio >= spike_multiplier * 2:
            severity = "high"
        elif ratio >= spike_multiplier * 1.5:
            severity = "medium"
        else:
            severity = "low"

        reason = (
            f"I/O spike detected: current rate ({current_rate:.0f} B/s) is "
            f"{ratio:.1f}× the baseline average ({baseline_rate:.0f} B/s), "
            f"exceeding the {spike_multiplier}× threshold."
        )

    return {
        "anomaly": anomaly,
        "type": "io_spike" if anomaly else "none",
        "severity": severity,
        "reason": reason,
        "current_rate": round(current_rate, 2),
        "baseline_rate": round(baseline_rate, 2),
        "ratio": round(ratio, 4),
        "num_observations": len(history),
        "thresholds": {
            "spike_multiplier": spike_multiplier,
            "min_rate": min_rate,
        },
    }


# ===================================================================
# I/O STALL DETECTION
# ===================================================================

def detect_io_stall(
    history: List[Dict[str, Any]],
    min_previous_rate: float = STALL_MIN_PREVIOUS_RATE,
    consecutive_zero: int = STALL_CONSECUTIVE_ZERO,
    zero_threshold: float = STALL_ZERO_THRESHOLD,
) -> Dict[str, Any]:
    """Detect when a previously active I/O process goes silent.

    === ALGORITHM ===
    1. Walk backward through the history to find the most recent
       non-zero I/O rate.
    2. Count how many consecutive observations at the end of the
       history have near-zero I/O.
    3. If the process was previously active (above ``min_previous_rate``)
       and has been silent for ``consecutive_zero`` observations, flag
       a stall.

    The idea: a process that was actively reading/writing and then
    suddenly stops may be hung, blocked on a lock, or deadlocked.

    Parameters:
        history             – List of I/O metrics dicts (oldest to newest).
        min_previous_rate   – The I/O rate a process must have had before
                              the stall to qualify.  Default: 50,000 B/s.
        consecutive_zero    – How many near-zero observations at the end
                              of history triggers a stall.  Default: 3.
        zero_threshold      – I/O rate below this is treated as "zero".
                              Default: 100 B/s.

    Returns:
        {
            "anomaly":              bool,
            "type":                 "io_stall" | "none",
            "severity":             str,
            "reason":               str,
            "last_active_rate":     float,
            "silent_observations":  int,
            "num_observations":     int,
            "thresholds":           { ... },
        }
    """
    if not isinstance(history, list) or len(history) < consecutive_zero + 1:
        return {
            "anomaly": False,
            "type": "none",
            "severity": "none",
            "reason": (
                f"Insufficient history for I/O stall detection "
                f"(need {consecutive_zero + 1}, got {len(history) if isinstance(history, list) else 0})."
            ),
            "last_active_rate": 0.0,
            "silent_observations": 0,
            "num_observations": len(history) if isinstance(history, list) else 0,
            "thresholds": {
                "min_previous_rate": min_previous_rate,
                "consecutive_zero": consecutive_zero,
                "zero_threshold": zero_threshold,
            },
        }

    # Count trailing near-zero observations.
    silent_count = 0
    for entry in reversed(history):
        rate = _safe_rate(entry)
        if rate < zero_threshold:
            silent_count += 1
        else:
            break

    # Find the last active rate (the one just before the stall started).
    last_active_rate = 0.0
    if silent_count < len(history):
        last_active_rate = _safe_rate(history[-(silent_count + 1)])

    anomaly = False
    severity = "none"
    reason = "No I/O stall detected — process I/O activity is normal."

    if silent_count >= consecutive_zero and last_active_rate >= min_previous_rate:
        anomaly = True
        if last_active_rate >= min_previous_rate * 10:
            severity = "critical"
        elif last_active_rate >= min_previous_rate * 5:
            severity = "high"
        elif last_active_rate >= min_previous_rate * 2:
            severity = "medium"
        else:
            severity = "low"

        reason = (
            f"I/O stall detected: process was previously active "
            f"({last_active_rate:.0f} B/s) but has shown near-zero I/O "
            f"({silent_count} consecutive observations below {zero_threshold:.0f} B/s). "
            f"Process may be hung or blocked."
        )

    return {
        "anomaly": anomaly,
        "type": "io_stall" if anomaly else "none",
        "severity": severity,
        "reason": reason,
        "last_active_rate": round(last_active_rate, 2),
        "silent_observations": silent_count,
        "num_observations": len(history),
        "thresholds": {
            "min_previous_rate": min_previous_rate,
            "consecutive_zero": consecutive_zero,
            "zero_threshold": zero_threshold,
        },
    }


# ===================================================================
# SUSTAINED HIGH I/O DETECTION
# ===================================================================

def detect_sustained_high_io(
    history: List[Dict[str, Any]],
    high_rate: float = SUSTAINED_HIGH_RATE,
    consecutive: int = SUSTAINED_CONSECUTIVE,
) -> Dict[str, Any]:
    """Detect a process maintaining extremely high I/O over time.

    === ALGORITHM ===
    1. Walk backward through the history and count how many of the
       most recent observations exceed ``high_rate``.
    2. If the count reaches ``consecutive``, flag sustained high I/O.

    The idea: a single high I/O observation may be normal (e.g.,
    copying a file).  But sustained high I/O over many observations
    suggests the process is monopolising disk bandwidth and may need
    to be throttled or investigated.

    Parameters:
        history       – List of I/O metrics dicts (oldest to newest).
        high_rate     – I/O rate (B/s) above which an observation is
                        considered "high".  Default: 5,000,000 (5 MB/s).
        consecutive   – Number of consecutive high observations needed.
                        Default: 5.

    Returns:
        {
            "anomaly":                bool,
            "type":                   "sustained_high_io" | "none",
            "severity":               str,
            "reason":                 str,
            "consecutive_high_count": int,
            "average_high_rate":      float,
            "num_observations":       int,
            "thresholds":             { ... },
        }
    """
    if not isinstance(history, list) or len(history) < consecutive:
        return {
            "anomaly": False,
            "type": "none",
            "severity": "none",
            "reason": (
                f"Insufficient history for sustained high I/O detection "
                f"(need {consecutive}, got {len(history) if isinstance(history, list) else 0})."
            ),
            "consecutive_high_count": 0,
            "average_high_rate": 0.0,
            "num_observations": len(history) if isinstance(history, list) else 0,
            "thresholds": {
                "high_rate": high_rate,
                "consecutive": consecutive,
            },
        }

    # Count trailing high-rate observations.
    high_count = 0
    high_rates: List[float] = []
    for entry in reversed(history):
        rate = _safe_rate(entry)
        if rate >= high_rate:
            high_count += 1
            high_rates.append(rate)
        else:
            break

    avg_high = sum(high_rates) / len(high_rates) if high_rates else 0.0

    anomaly = False
    severity = "none"
    reason = "No sustained high I/O detected — rate is within limits."

    if high_count >= consecutive:
        anomaly = True
        if high_count >= consecutive * 3:
            severity = "critical"
        elif high_count >= consecutive * 2:
            severity = "high"
        elif high_count >= int(consecutive * 1.5) + 1:
            severity = "medium"
        else:
            severity = "low"

        reason = (
            f"Sustained high I/O detected: process has maintained "
            f">= {high_rate:.0f} B/s for {high_count} consecutive "
            f"observations (average: {avg_high:.0f} B/s).  Process "
            f"may be monopolising disk bandwidth."
        )

    return {
        "anomaly": anomaly,
        "type": "sustained_high_io" if anomaly else "none",
        "severity": severity,
        "reason": reason,
        "consecutive_high_count": high_count,
        "average_high_rate": round(avg_high, 2),
        "num_observations": len(history),
        "thresholds": {
            "high_rate": high_rate,
            "consecutive": consecutive,
        },
    }


# ===================================================================
# READ/WRITE RATIO SHIFT DETECTION
# ===================================================================

def detect_rw_ratio_shift(
    history: List[Dict[str, Any]],
    shift_multiplier: float = RATIO_SHIFT_MULTIPLIER,
    min_history: int = RATIO_SHIFT_MIN_HISTORY,
    min_ratio: float = RATIO_SHIFT_MIN_RATIO,
) -> Dict[str, Any]:
    """Detect a dramatic shift in a process's read/write ratio.

    === ALGORITHM ===
    1. Compute the average read/write ratio over the last
       ``min_history`` observations (excluding the latest).
    2. Compare the latest observation's ratio to this baseline.
    3. If the ratio has changed by more than ``shift_multiplier``,
       flag a shift.

    This detects changes in workload character, e.g., a database
    switching from read-heavy to write-heavy.

    Parameters:
        history           – List of I/O metrics dicts (each must contain
                            ``read_write_ratio``).
        shift_multiplier  – Factor by which the ratio must change.
                            Default: 5.0.
        min_history       – Minimum observations required.  Default: 5.
        min_ratio         – Ignore ratios below this value (near-zero
                            ratios are unreliable).  Default: 0.1.

    Returns:
        {
            "anomaly":          bool,
            "type":             "rw_ratio_shift" | "none",
            "severity":         str,
            "reason":           str,
            "current_ratio":    float,
            "baseline_ratio":   float,
            "ratio_of_ratios":  float,
            "num_observations": int,
            "thresholds":       { ... },
        }
    """
    if not isinstance(history, list) or len(history) < min_history + 1:
        return {
            "anomaly": False,
            "type": "none",
            "severity": "none",
            "reason": (
                f"Insufficient history for R/W ratio shift detection "
                f"(need {min_history + 1}, got {len(history) if isinstance(history, list) else 0})."
            ),
            "current_ratio": 0.0,
            "baseline_ratio": 0.0,
            "ratio_of_ratios": 0.0,
            "num_observations": len(history) if isinstance(history, list) else 0,
            "thresholds": {
                "shift_multiplier": shift_multiplier,
                "min_ratio": min_ratio,
            },
        }

    current_ratio = _safe_ratio(history[-1])

    baseline_ratios = []
    for h in history[:-1]:
        r = _safe_ratio(h)
        if r >= min_ratio:
            baseline_ratios.append(r)

    if not baseline_ratios:
        return {
            "anomaly": False,
            "type": "none",
            "severity": "none",
            "reason": (
                "No reliable baseline R/W ratios available "
                "(all ratios below minimum threshold)."
            ),
            "current_ratio": round(current_ratio, 4),
            "baseline_ratio": 0.0,
            "ratio_of_ratios": 0.0,
            "num_observations": len(history),
            "thresholds": {
                "shift_multiplier": shift_multiplier,
                "min_ratio": min_ratio,
            },
        }

    baseline_ratio = sum(baseline_ratios) / len(baseline_ratios)

    # Compute ratio of ratios (symmetric: max/min to avoid division by near-zero).
    if baseline_ratio > 0 and current_ratio > 0:
        ratio_of_ratios = max(
            current_ratio / baseline_ratio,
            baseline_ratio / current_ratio,
        )
    else:
        ratio_of_ratios = 0.0

    anomaly = False
    severity = "none"
    reason = "R/W ratio is stable relative to recent history."

    if (baseline_ratio >= min_ratio
            and current_ratio >= min_ratio
            and ratio_of_ratios >= shift_multiplier):
        anomaly = True
        if ratio_of_ratios >= shift_multiplier * 5:
            severity = "critical"
        elif ratio_of_ratios >= shift_multiplier * 3:
            severity = "high"
        elif ratio_of_ratios >= shift_multiplier * 2:
            severity = "medium"
        else:
            severity = "low"

        reason = (
            f"R/W ratio shift detected: current ratio ({current_ratio:.2f}) "
            f"is {ratio_of_ratios:.1f}× the baseline ({baseline_ratio:.2f}), "
            f"exceeding the {shift_multiplier}× threshold.  Workload "
            f"character may have changed."
        )

    return {
        "anomaly": anomaly,
        "type": "rw_ratio_shift" if anomaly else "none",
        "severity": severity,
        "reason": reason,
        "current_ratio": round(current_ratio, 4),
        "baseline_ratio": round(baseline_ratio, 4),
        "ratio_of_ratios": round(ratio_of_ratios, 4),
        "num_observations": len(history),
        "thresholds": {
            "shift_multiplier": shift_multiplier,
            "min_ratio": min_ratio,
        },
    }


# ===================================================================
# Batch analysis helper (convenience function)
# ===================================================================

def analyze_io_health(
    history: List[Dict[str, Any]],
    spike_multiplier: float = SPIKE_MULTIPLIER,
    spike_min_history: int = SPIKE_MIN_HISTORY,
    spike_min_rate: float = SPIKE_MIN_RATE,
    stall_min_previous_rate: float = STALL_MIN_PREVIOUS_RATE,
    stall_consecutive_zero: int = STALL_CONSECUTIVE_ZERO,
    stall_zero_threshold: float = STALL_ZERO_THRESHOLD,
    sustained_high_rate: float = SUSTAINED_HIGH_RATE,
    sustained_consecutive: int = SUSTAINED_CONSECUTIVE,
    ratio_shift_multiplier: float = RATIO_SHIFT_MULTIPLIER,
    ratio_shift_min_history: int = RATIO_SHIFT_MIN_HISTORY,
    ratio_shift_min_ratio: float = RATIO_SHIFT_MIN_RATIO,
) -> Dict[str, Any]:
    """Run all I/O anomaly detectors in one call.

    Convenience function for the dashboard.  Runs spike, stall,
    sustained-high, and ratio-shift detection on the given history
    and returns a combined result.

    Parameters:
        history                 – List of I/O metrics dicts (oldest to newest).
        spike_multiplier        – See detect_io_spike().
        spike_min_history       – See detect_io_spike().
        spike_min_rate          – See detect_io_spike().
        stall_min_previous_rate – See detect_io_stall().
        stall_consecutive_zero  – See detect_io_stall().
        stall_zero_threshold    – See detect_io_stall().
        sustained_high_rate     – See detect_sustained_high_io().
        sustained_consecutive   – See detect_sustained_high_io().
        ratio_shift_multiplier  – See detect_rw_ratio_shift().
        ratio_shift_min_history – See detect_rw_ratio_shift().
        ratio_shift_min_ratio   – See detect_rw_ratio_shift().

    Returns:
        {
            "io_spike":          { ... result from detect_io_spike ... },
            "io_stall":          { ... result from detect_io_stall ... },
            "sustained_high_io": { ... result from detect_sustained_high_io ... },
            "rw_ratio_shift":    { ... result from detect_rw_ratio_shift ... },
            "any_anomaly":       bool,
            "most_severe":       str,  # highest severity across detectors
        }
    """
    spike = detect_io_spike(
        history,
        spike_multiplier=spike_multiplier,
        min_history=spike_min_history,
        min_rate=spike_min_rate,
    )
    stall = detect_io_stall(
        history,
        min_previous_rate=stall_min_previous_rate,
        consecutive_zero=stall_consecutive_zero,
        zero_threshold=stall_zero_threshold,
    )
    sustained = detect_sustained_high_io(
        history,
        high_rate=sustained_high_rate,
        consecutive=sustained_consecutive,
    )
    ratio = detect_rw_ratio_shift(
        history,
        shift_multiplier=ratio_shift_multiplier,
        min_history=ratio_shift_min_history,
        min_ratio=ratio_shift_min_ratio,
    )

    severity_order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    results = [spike, stall, sustained, ratio]
    most_severe = "none"
    for r in results:
        s = r.get("severity", "none")
        if severity_order.get(s, 0) > severity_order.get(most_severe, 0):
            most_severe = s

    return {
        "io_spike": spike,
        "io_stall": stall,
        "sustained_high_io": sustained,
        "rw_ratio_shift": ratio,
        "any_anomaly": any(r.get("anomaly", False) for r in results),
        "most_severe": most_severe,
    }
