"""
intelligence/memory_anomaly.py – Memory Anomaly Detection
OS Sentinel – Teammate B (Memory & I/O Subsystem) – Phase 4B

=== OS CONCEPT: MEMORY ANOMALIES ===

Operating systems can exhibit two common memory-related anomalies:

1. **Memory Leak**
   A process continuously allocates memory without ever freeing it.  Over
   time, memory usage grows steadily until the system runs out of RAM and
   starts thrashing or killing processes (OOM killer).

   Detection heuristic:  If memory usage increases consistently over a
   configurable number of observations, a possible leak is flagged.

2. **Thrashing**
   When the system is so low on physical RAM that it spends more time
   swapping pages in and out of disk than doing useful work.  This is
   characterized by HIGH memory pressure combined with HIGH page-fault
   activity.

   Detection heuristic:  If memory usage exceeds a threshold AND the
   page fault rate exceeds a threshold, possible thrashing is flagged.

=== ARCHITECTURE ===

    System  →  Memory Monitor  →  Historical Measurements  →  Anomaly Detector  →  Alert

The anomaly detector is **completely decoupled** from psutil.  It accepts
plain lists/dicts of numeric measurements, making it fully testable with
mock data and reusable by the dashboard and shared Alert Engine.

=== DESIGN PHILOSOPHY ===

- No machine learning.  Only explainable heuristics based on OS theory.
- Conservative: avoids false positives via configurable thresholds.
- Returns structured data: severity, reason, metrics, actionable info.
- Never claims certainty — results say "possible" anomaly.

=== SEVERITY LEVELS ===

  "none"     – No anomaly detected.
  "low"      – Early warning signs present.
  "medium"   – Anomaly pattern is forming.
  "high"     – Strong anomaly pattern detected.
  "critical" – Anomaly pattern is very strong; immediate attention needed.
"""

from typing import Any, Dict, List, Optional


# ===================================================================
# Input validation
# ===================================================================

def _validate_usage_history(
    history: List[float],
    min_length: int,
    param_name: str = "history",
) -> None:
    """Validate a list of numeric measurements.

    Raises:
        ValueError – if the history is too short or contains non-numeric values.
    """
    if not isinstance(history, list):
        raise ValueError(f"{param_name} must be a list")

    if len(history) < min_length:
        raise ValueError(
            f"{param_name} must have at least {min_length} observations, "
            f"got {len(history)}"
        )

    for i, val in enumerate(history):
        if not isinstance(val, (int, float)):
            raise ValueError(
                f"{param_name}[{i}] must be numeric, "
                f"got {type(val).__name__}"
            )


def _validate_threshold(value: float, name: str) -> None:
    """Ensure a threshold is a non-negative number.

    Raises:
        ValueError – if the value is not valid.
    """
    if not isinstance(value, (int, float)) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative number, got {value}"
        )


# ===================================================================
# MEMORY LEAK DETECTION
# ===================================================================

def detect_memory_leak(
    usage_history: List[float],
    threshold: float = 1.0,
    min_observations: int = 5,
    tolerance: int = 1,
) -> Dict[str, Any]:
    """Detect a possible memory leak from a sequence of memory usage values.

    === ALGORITHM (simple explanation) ===
    1. We look at how memory usage changes between consecutive observations.
    2. We count how many times usage INCREASED (by more than `threshold`).
    3. We allow up to `tolerance` non-increasing observations in a row
       before breaking the "increasing" streak.
    4. If the number of increasing observations is high relative to the
       total, we flag a possible leak.

    The idea:  A real memory leak shows a *consistent upward trend*.
    Normal memory fluctuation goes up AND down.  If memory almost always
    goes up, something is probably leaking.

    Parameters:
        usage_history    – Chronological memory usage measurements
                           (e.g., MB, %, or any numeric unit).
        threshold        – Minimum increase between two consecutive
                           observations to count as "rising".  Helps
                           ignore tiny fluctuations (noise).  Default: 1.0.
        min_observations – Minimum number of observations required.
                           With too few data points, detection is unreliable.
                           Default: 5.
        tolerance        – Number of consecutive non-increasing observations
                           allowed before we stop counting the streak.
                           Default: 1 (allows one plateau/dip in the trend).

    Returns:
        {
            "anomaly":         bool,
            "type":            "memory_leak" | "none",
            "severity":        str,
            "reason":          str,
            "current_usage":   float,
            "starting_usage":  float,
            "total_increase":  float,
            "increasing_pct":  float,   # % of steps that showed increase
            "num_observations": int,
            "threshold":       float,
        }
    """
    _validate_usage_history(usage_history, min_observations, "usage_history")
    _validate_threshold(threshold, "threshold")

    n = len(usage_history)
    current  = usage_history[-1]
    starting = usage_history[0]
    total_increase = current - starting

    # Count how many consecutive-pair steps show a meaningful increase.
    increasing_count = 0
    non_increasing_streak = 0

    for i in range(1, n):
        diff = usage_history[i] - usage_history[i - 1]
        if diff >= threshold:
            increasing_count += 1
            non_increasing_streak = 0
        else:
            non_increasing_streak += 1

    total_steps = n - 1
    increasing_pct = round((increasing_count / total_steps) * 100, 2) if total_steps > 0 else 0.0

    # --- Decision logic ---
    # A leak is "possible" when a high proportion of steps are increasing.
    anomaly = False
    severity = "none"
    reason = "Memory usage is stable — no leak pattern detected."

    if increasing_pct >= 90:
        anomaly = True
        severity = "critical"
        reason = (
            f"Possible memory leak detected: {increasing_pct}% of observations "
            f"show increasing memory usage (total increase: {total_increase:.2f})."
        )
    elif increasing_pct >= 75:
        anomaly = True
        severity = "high"
        reason = (
            f"Possible memory leak detected: {increasing_pct}% of observations "
            f"show increasing memory usage."
        )
    elif increasing_pct >= 60:
        anomaly = True
        severity = "medium"
        reason = (
            f"Possible memory leak pattern forming: {increasing_pct}% of "
            f"observations show increasing memory usage."
        )
    elif increasing_pct >= 50:
        anomaly = True
        severity = "low"
        reason = (
            f"Early warning: {increasing_pct}% of observations show "
            f"increasing memory usage.  Monitor closely."
        )

    return {
        "anomaly":          anomaly,
        "type":             "memory_leak" if anomaly else "none",
        "severity":         severity,
        "reason":           reason,
        "current_usage":    current,
        "starting_usage":   starting,
        "total_increase":   round(total_increase, 4),
        "increasing_pct":   increasing_pct,
        "num_observations": n,
        "threshold":        threshold,
    }


# ===================================================================
# THRASHING DETECTION
# ===================================================================

def detect_thrashing(
    memory_usage_pct: float,
    page_fault_rate: float,
    memory_threshold: float = 85.0,
    page_fault_threshold: float = 50.0,
    swap_usage_pct: Optional[float] = None,
    swap_threshold: float = 70.0,
) -> Dict[str, Any]:
    """Detect possible thrashing from current memory and page-fault metrics.

    === CONCEPT (simple explanation) ===
    Thrashing happens when the OS spends most of its time swapping pages
    instead of running programs.  Two things must be true at once:
      1. Memory is nearly full (high memory usage).
      2. Page faults are very frequent (high page-fault rate).

    Optionally, heavy swap usage provides additional evidence.

    This function takes a SINGLE measurement (point-in-time snapshot).
    For trend analysis, call it on each observation in a time series
    and count how many trigger the alert.

    Parameters:
        memory_usage_pct     – Current memory usage as a percentage (0–100).
        page_fault_rate      – Current page fault rate (faults per second,
                               or a normalized 0–100 score).
        memory_threshold     – Memory usage % above which we consider
                               pressure "high".  Default: 85%.
        page_fault_threshold – Page fault rate above which we consider
                               activity "high".  Default: 50.
        swap_usage_pct       – Optional swap usage percentage (0–100).
        swap_threshold       – Swap usage % above which we add evidence.
                               Default: 70%.

    Returns:
        {
            "anomaly":  bool,
            "type":     "thrashing" | "none",
            "severity": str,
            "reason":   str,
            "metrics":  {
                "memory_usage_pct":  float,
                "page_fault_rate":   float,
                "swap_usage_pct":    float | None,
            },
            "thresholds": {
                "memory_threshold":      float,
                "page_fault_threshold":  float,
                "swap_threshold":        float,
            },
        }

    Raises:
        ValueError – if memory_usage_pct or page_fault_rate is invalid.
    """
    # --- Input validation ---
    if not isinstance(memory_usage_pct, (int, float)):
        raise ValueError(
            f"memory_usage_pct must be numeric, got "
            f"{type(memory_usage_pct).__name__}"
        )
    if not isinstance(page_fault_rate, (int, float)):
        raise ValueError(
            f"page_fault_rate must be numeric, got "
            f"{type(page_fault_rate).__name__}"
        )
    if not (0 <= memory_usage_pct <= 100):
        raise ValueError(
            f"memory_usage_pct must be in [0, 100], got {memory_usage_pct}"
        )
    if page_fault_rate < 0:
        raise ValueError(
            f"page_fault_rate must be non-negative, got {page_fault_rate}"
        )
    if swap_usage_pct is not None:
        if not isinstance(swap_usage_pct, (int, float)):
            raise ValueError(
                f"swap_usage_pct must be numeric or None, got "
                f"{type(swap_usage_pct).__name__}"
            )
        if not (0 <= swap_usage_pct <= 100):
            raise ValueError(
                f"swap_usage_pct must be in [0, 100], got {swap_usage_pct}"
            )

    _validate_threshold(memory_threshold, "memory_threshold")
    _validate_threshold(page_fault_threshold, "page_fault_threshold")
    _validate_threshold(swap_threshold, "swap_threshold")

    # --- Detection logic ---
    high_memory    = memory_usage_pct >= memory_threshold
    high_faults    = page_fault_rate >= page_fault_threshold
    high_swap      = (swap_usage_pct is not None and
                      swap_usage_pct >= swap_threshold)

    # Evidence scoring (0–3).
    evidence = sum([high_memory, high_faults, high_swap])

    anomaly = False
    severity = "none"
    reason = "No thrashing detected — system resources within normal limits."

    if high_memory and high_faults:
        # Both core conditions met.
        anomaly = True

        if high_swap:
            severity = "critical"
            reason = (
                f"Possible thrashing detected: memory usage "
                f"({memory_usage_pct:.1f}%) exceeds threshold "
                f"({memory_threshold}%), page fault rate "
                f"({page_fault_rate:.1f}) exceeds threshold "
                f"({page_fault_threshold}), AND swap usage "
                f"({swap_usage_pct:.1f}%) is high.  The system is likely "
                f"spending excessive time swapping pages."
            )
        else:
            severity = "high"
            reason = (
                f"Possible thrashing detected: memory usage "
                f"({memory_usage_pct:.1f}%) exceeds threshold "
                f"({memory_threshold}%) and page fault rate "
                f"({page_fault_rate:.1f}) exceeds threshold "
                f"({page_fault_threshold}).  Consider freeing memory or "
                f"adding RAM."
            )

    elif high_memory and not high_faults:
        # Memory is high but faults are manageable — warning only.
        severity = "low"
        reason = (
            f"Memory usage ({memory_usage_pct:.1f}%) is above threshold "
            f"({memory_threshold}%), but page fault rate "
            f"({page_fault_rate:.1f}) is within limits.  No thrashing yet, "
            f"but monitor closely."
        )

    return {
        "anomaly":    anomaly,
        "type":       "thrashing" if anomaly else "none",
        "severity":   severity,
        "reason":     reason,
        "metrics": {
            "memory_usage_pct": memory_usage_pct,
            "page_fault_rate":  page_fault_rate,
            "swap_usage_pct":   swap_usage_pct,
        },
        "thresholds": {
            "memory_threshold":     memory_threshold,
            "page_fault_threshold": page_fault_threshold,
            "swap_threshold":       swap_threshold,
        },
    }


# ===================================================================
# Batch analysis helper (for time-series dashboard data)
# ===================================================================

def analyze_memory_health(
    usage_history: List[float],
    current_memory_pct: float,
    current_page_fault_rate: float,
    leak_threshold: float = 1.0,
    leak_min_observations: int = 5,
    thrash_memory_threshold: float = 85.0,
    thrash_fault_threshold: float = 50.0,
    swap_usage_pct: Optional[float] = None,
    swap_threshold: float = 70.0,
) -> Dict[str, Any]:
    """Run both memory leak and thrashing detection in one call.

    This is a convenience function for the dashboard.  It runs both
    detectors and returns a combined result.

    Parameters:
        usage_history             – Historical memory usage for leak detection.
        current_memory_pct        – Current memory % for thrashing detection.
        current_page_fault_rate   – Current page fault rate.
        leak_threshold            – See detect_memory_leak().
        leak_min_observations     – See detect_memory_leak().
        thrash_memory_threshold   – See detect_thrashing().
        thrash_fault_threshold    – See detect_thrashing().
        swap_usage_pct            – Optional current swap usage %.
        swap_threshold            – See detect_thrashing().

    Returns:
        {
            "memory_leak": { ... result from detect_memory_leak ... },
            "thrashing":   { ... result from detect_thrashing ... },
            "any_anomaly": bool,
        }
    """
    leak_result = detect_memory_leak(
        usage_history,
        threshold=leak_threshold,
        min_observations=leak_min_observations,
    )
    thrash_result = detect_thrashing(
        current_memory_pct,
        current_page_fault_rate,
        memory_threshold=thrash_memory_threshold,
        page_fault_threshold=thrash_fault_threshold,
        swap_usage_pct=swap_usage_pct,
        swap_threshold=swap_threshold,
    )

    return {
        "memory_leak": leak_result,
        "thrashing":   thrash_result,
        "any_anomaly": leak_result["anomaly"] or thrash_result["anomaly"],
    }
