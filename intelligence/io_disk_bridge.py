"""Integration bridge between IOPulse I/O telemetry and disk scheduling.

This module connects the observed process-level I/O metrics (from
``intelligence.io_metrics``) with the existing disk scheduling algorithms
(in ``disk_io/``) by providing:

1. A deterministic transformation from observed I/O activity into a
   **simulated** disk request workload (cylinder positions).
2. A comparative analysis that runs FCFS, SSTF, SCAN, and C-SCAN on
   the simulated workload and recommends the best algorithm.

=== IMPORTANT: SIMULATION vs. OBSERVATION ===

Real process I/O telemetry (e.g. psutil.io_counters()) provides byte
counts and operation counts — NOT physical disk-cylinder locations.
Operating systems do not expose disk-head positions to user-space.

Therefore this module clearly labels all cylinder values as
**SIMULATED**.  The transformation from observed I/O to cylinder
positions is a deterministic, reproducible mapping used solely for
the purpose of evaluating disk scheduling algorithms under realistic
I/O workload patterns.  The cylinder values do NOT represent actual
physical disk locations.

=== TRANSFORMATION PIPELINE ===

    Observed process I/O metrics
            |
            v
    Normalised I/O intensity per process  (0.0 – 1.0)
            |
            v
    Deterministic cylinder mapping  (hash-based, bounded to [0, disk_size))
            |
            v
    Simulated request queue  (list of cylinder positions)
            |
            v
    FCFS / SSTF / SCAN / C-SCAN  (existing algorithms, unchanged)
            |
            v
    Comparative analysis  +  recommendation

=== DESIGN PRINCIPLES ===

- The existing disk scheduling algorithms are called via their public
  API — they are NOT reimplemented or modified.
- The transformation is fully deterministic: identical inputs always
  produce identical request queues and identical recommendations.
- No random values are used anywhere.
- All thresholds are configurable.
"""

from __future__ import annotations

from hashlib import md5
from math import isinf, isnan
from typing import Any, Dict, List, Tuple

from disk_io.fcfs import fcfs
from disk_io.sstf import sstf
from disk_io.scan import scan
from disk_io.cscan import cscan


# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

DEFAULT_DISK_SIZE: int = 200
DEFAULT_HEAD_POSITION: int = 0
DEFAULT_DIRECTION: str = "right"

# Minimum I/O rate (B/s) below which a process is ignored for request
# generation.  Prevents idle processes from generating spurious requests.
MIN_IO_RATE: float = 100.0

# Maximum number of simulated requests per process.  Prevents a single
# very active process from dominating the request queue.
MAX_REQUESTS_PER_PROCESS: int = 10

# Minimum number of requests to generate.  If the computed count is
# lower, we still generate at least this many (if there is any I/O).
MIN_REQUESTS_TOTAL: int = 1


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


def _deterministic_cylinder(
    pid: int,
    byte_count: int,
    disk_size: int,
    salt: str = "",
) -> int:
    """Map a (pid, byte_count) pair to a cylinder in [0, disk_size).

    === ALGORITHM ===
    1. Construct the key: ``f"{pid}:{byte_count}:{salt}"``.
    2. Compute MD5 hex digest of the key.
    3. Interpret the first 8 hex characters as an integer.
    4. Reduce modulo disk_size to get a value in [0, disk_size).

    This is fully deterministic: the same inputs always produce the
    same cylinder.  The use of MD5 is NOT for security — it is simply
    a well-known hash function that distributes values uniformly.

    Parameters:
        pid        – Process ID (or any integer identifier).
        byte_count – A byte count (read_bytes, write_bytes, or total).
        disk_size  – Total number of cylinders.
        salt       – Optional extra string to differentiate mappings
                     (e.g. "read" vs "write").

    Returns:
        An integer cylinder position in [0, disk_size).
    """
    key = f"{pid}:{byte_count}:{salt}".encode("utf-8")
    digest = md5(key).hexdigest()
    # Use first 8 hex chars → up to 32-bit int → modulo disk_size.
    numeric = int(digest[:8], 16)
    return numeric % disk_size


# ---------------------------------------------------------------------------
# Request workload derivation
# ---------------------------------------------------------------------------

def derive_request_workload(
    io_metrics_list: List[Dict[str, Any]],
    disk_size: int = DEFAULT_DISK_SIZE,
    min_io_rate: float = MIN_IO_RATE,
    max_requests_per_process: int = MAX_REQUESTS_PER_PROCESS,
) -> List[int]:
    """Derive a deterministic simulated request queue from process I/O metrics.

    === TRANSFORMATION ===

    For each process with meaningful I/O activity:

    1. **Compute I/O intensity**: normalise total_io_bytes_per_sec
       relative to the maximum across all processes → value in [0, 1].

    2. **Determine request count**: scale by intensity → between 1 and
       ``max_requests_per_process`` requests per process.

    3. **Generate cylinder positions**: for each request, hash
       (pid, cumulative_bytes, index) to produce a deterministic
       cylinder in [0, disk_size).

    4. **Separate reads and writes**: read-heavy processes generate
       requests biased toward the lower half of the disk; write-heavy
       processes toward the upper half.  This creates a realistic
       workload distribution.

    All outputs are explicitly SIMULATED cylinder positions.

    Parameters:
        io_metrics_list:
            List of I/O metrics dicts as produced by
            ``ProcessIOCollector.collect_all()`` or the classifier.
            Each dict should contain at minimum:
              - pid                           (int)
              - total_io_bytes_per_sec         (float)
              - read_bytes_per_sec             (float, optional)
              - write_bytes_per_sec            (float, optional)
              - read_count                     (int, optional)
              - write_count                    (int, optional)

        disk_size:
            Total number of simulated cylinders.  All generated
            positions will be in [0, disk_size).  Default: 200.

        min_io_rate:
            Processes below this I/O rate (B/s) are excluded.
            Default: 100 B/s.

        max_requests_per_process:
            Cap on requests generated per process.  Default: 10.

    Returns:
        A list of integer cylinder positions (the simulated request
        queue).  May be empty if no processes have meaningful I/O.

    === EXAMPLE ===

    >>> metrics = [
    ...     {"pid": 100, "total_io_bytes_per_sec": 5_000_000,
    ...      "read_bytes_per_sec": 3_000_000, "write_bytes_per_sec": 2_000_000},
    ...     {"pid": 200, "total_io_bytes_per_sec": 1_000_000,
    ...      "read_bytes_per_sec": 800_000, "write_bytes_per_sec": 200_000},
    ... ]
    >>> queue = derive_request_workload(metrics, disk_size=200)
    >>> all(0 <= c < 200 for c in queue)
    True
    """
    if not isinstance(io_metrics_list, list) or not io_metrics_list:
        return []

    if disk_size <= 0:
        return []

    # Filter to processes with meaningful I/O.
    active: List[Dict[str, Any]] = []
    for m in io_metrics_list:
        if not isinstance(m, dict):
            continue
        rate = _safe_float(m.get("total_io_bytes_per_sec"), 0.0)
        if rate >= min_io_rate:
            active.append(m)

    if not active:
        return []

    # Compute I/O intensities (normalised to [0, 1]).
    max_rate = max(
        _safe_float(m.get("total_io_bytes_per_sec"), 0.0) for m in active
    )
    if max_rate <= 0:
        return []

    requests: List[int] = []

    for m in active:
        pid = _safe_pid(m)
        total_rate = _safe_float(m.get("total_io_bytes_per_sec"), 0.0)
        read_count = int(_safe_float(m.get("read_count"), 0.0))
        write_count = int(_safe_float(m.get("write_count"), 0.0))

        intensity = total_rate / max_rate  # in (0, 1]

        # Number of requests proportional to intensity.
        n_requests = max(
            1,
            min(
                max_requests_per_process,
                round(intensity * max_requests_per_process),
            ),
        )

        for i in range(n_requests):
            # Use cumulative bytes for uniqueness across requests.
            if i % 2 == 0:
                # Read-biased request: lower half of disk.
                byte_seed = read_count + i
                salt = "read"
                half = disk_size // 2
            else:
                # Write-biased request: upper half of disk.
                byte_seed = write_count + i
                salt = "write"
                half = disk_size // 2

            cylinder = _deterministic_cylinder(pid, byte_seed, disk_size, salt)

            # Bias read requests toward lower half, write toward upper half.
            if i % 2 == 0:
                cylinder = cylinder % half  # [0, half)
            else:
                cylinder = half + (cylinder % (disk_size - half))  # [half, disk_size)

            requests.append(int(cylinder))

    return requests


def _safe_pid(metrics: Dict[str, Any]) -> int:
    """Extract PID from metrics, defaulting to 0."""
    try:
        return int(metrics.get("pid", 0))
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Disk scheduling comparative analysis
# ---------------------------------------------------------------------------

def analyze_disk_scheduling(
    request_queue: List[int],
    head_position: int = DEFAULT_HEAD_POSITION,
    disk_size: int = DEFAULT_DISK_SIZE,
    direction: str = DEFAULT_DIRECTION,
) -> Dict[str, Any]:
    """Run all four disk scheduling algorithms and recommend the best one.

    This function calls the existing ``disk_io`` algorithms via their
    public API.  It does NOT reimplement any scheduling logic.

    Parameters:
        request_queue  – List of simulated cylinder positions to service.
        head_position  – Starting position of the disk head.
        disk_size      – Total number of cylinders.
        direction      – Initial sweep direction for SCAN/C-SCAN
                         ("left" or "right").

    Returns:
        {
            "request_count":    int,
            "disk_size":        int,
            "head_position":    int,
            "direction":        str,
            "results": {
                "FCFS":    { ... result from disk_io.fcfs ... },
                "SSTF":    { ... result from disk_io.sstf ... },
                "SCAN":    { ... result from disk_io.scan ... },
                "C-SCAN":  { ... result from disk_io.cscan ... },
            },
            "total_head_movements": {
                "FCFS":   int,
                "SSTF":   int,
                "SCAN":   int,
                "C-SCAN": int,
            },
            "recommended_algorithm": str,
            "reason":               str,
        }

    Raises:
        ValueError – if disk_size, head_position, or direction is invalid.
    """
    _validate_analysis_inputs(head_position, disk_size, direction)

    if not request_queue:
        return _empty_analysis_result(head_position, disk_size, direction)

    # Run all four algorithms.  Each returns its standard result dict.
    fcfs_result = fcfs(request_queue, head_position, disk_size)
    sstf_result = sstf(request_queue, head_position, disk_size)
    scan_result = scan(request_queue, head_position, disk_size, direction)
    cscan_result = cscan(request_queue, head_position, disk_size, direction)

    movements = {
        "FCFS": fcfs_result["total_head_movement"],
        "SSTF": sstf_result["total_head_movement"],
        "SCAN": scan_result["total_head_movement"],
        "C-SCAN": cscan_result["total_head_movement"],
    }

    # Recommend the algorithm with the lowest total head movement.
    # Tie-breaking: deterministic alphabetical order (C-SCAN, FCFS, SCAN, SSTF).
    # This ensures reproducibility when two algorithms tie.
    recommended, reason = _recommend_algorithm(movements)

    return {
        "request_count": len(request_queue),
        "disk_size": disk_size,
        "head_position": head_position,
        "direction": direction,
        "results": {
            "FCFS": fcfs_result,
            "SSTF": sstf_result,
            "SCAN": scan_result,
            "C-SCAN": cscan_result,
        },
        "total_head_movements": movements,
        "recommended_algorithm": recommended,
        "reason": reason,
    }


def analyze_process_io_scheduling(
    io_metrics_list: List[Dict[str, Any]],
    head_position: int = DEFAULT_HEAD_POSITION,
    disk_size: int = DEFAULT_DISK_SIZE,
    direction: str = DEFAULT_DIRECTION,
    min_io_rate: float = MIN_IO_RATE,
    max_requests_per_process: int = MAX_REQUESTS_PER_PROCESS,
) -> Dict[str, Any]:
    """End-to-end analysis: process I/O telemetry → disk scheduling comparison.

    This is the main entry point for the IOPulse bridge.  It:

    1. Derives a simulated request workload from process I/O metrics.
    2. Runs all four disk scheduling algorithms on the workload.
    3. Returns a combined result with both the raw telemetry summary
       and the scheduling comparison.

    Parameters:
        io_metrics_list:         See derive_request_workload().
        head_position:           See analyze_disk_scheduling().
        disk_size:               See analyze_disk_scheduling().
        direction:               See analyze_disk_scheduling().
        min_io_rate:             See derive_request_workload().
        max_requests_per_process: See derive_request_workload().

    Returns:
        {
            "observed_processes": [
                {
                    "pid":                      int,
                    "name":                     str,
                    "total_io_bytes_per_sec":   float,
                    "classification":           str | None,
                },
                ...
            ],
            "simulated_request_queue": [int],
            "simulation_note":         str,
            "scheduling_analysis":     { ... result from analyze_disk_scheduling ... },
        }
    """
    # Summarise observed processes.
    observed = []
    for m in (io_metrics_list or []):
        if not isinstance(m, dict):
            continue
        observed.append({
            "pid": _safe_pid(m),
            "name": str(m.get("name", "unknown") or "unknown"),
            "total_io_bytes_per_sec": round(
                _safe_float(m.get("total_io_bytes_per_sec"), 0.0), 2
            ),
            "classification": m.get("classification"),
        })

    # Derive simulated workload.
    queue = derive_request_workload(
        io_metrics_list or [],
        disk_size=disk_size,
        min_io_rate=min_io_rate,
        max_requests_per_process=max_requests_per_process,
    )

    # Run scheduling analysis.
    analysis = analyze_disk_scheduling(
        queue,
        head_position=head_position,
        disk_size=disk_size,
        direction=direction,
    )

    return {
        "observed_processes": observed,
        "simulated_request_queue": queue,
        "simulation_note": (
            "Simulated disk request workload derived from observed "
            "process I/O activity.  Cylinder positions are deterministic "
            "mappings of I/O metrics and do not represent actual physical "
            "disk locations."
        ),
        "scheduling_analysis": analysis,
    }


# ---------------------------------------------------------------------------
# Recommendation logic
# ---------------------------------------------------------------------------

# Deterministic tie-breaking order (alphabetical).
_TIE_BREAK_ORDER = ["C-SCAN", "FCFS", "SCAN", "SSTF"]


def _recommend_algorithm(movements: Dict[str, int]) -> Tuple[str, str]:
    """Pick the algorithm with the lowest total head movement.

    Tie-breaking: deterministic alphabetical order (C-SCAN < FCFS <
    SCAN < SSTF).  This ensures the same result every time.

    Returns:
        (algorithm_name, reason_string)
    """
    min_movement = min(movements.values())

    # Collect all algorithms that achieve the minimum.
    tied = [name for name, mv in movements.items() if mv == min_movement]

    # Sort by our deterministic tie-breaking order.
    tied.sort(key=lambda name: _TIE_BREAK_ORDER.index(name))
    winner = tied[0]

    reason = (
        f"{winner} produced the lowest simulated total head movement "
        f"({min_movement}) for this request workload."
    )
    if len(tied) > 1:
        reason += (
            f"  Tied with {', '.join(t for t in tied if t != winner)}; "
            f"deterministic tie-breaking selected {winner}."
        )

    return winner, reason


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_analysis_inputs(
    head_position: int,
    disk_size: int,
    direction: str,
) -> None:
    """Validate parameters for analyze_disk_scheduling.

    Raises:
        ValueError – if any parameter is invalid.
    """
    if disk_size <= 0:
        raise ValueError(f"disk_size must be positive, got {disk_size}")

    if not (0 <= head_position < disk_size):
        raise ValueError(
            f"head_position ({head_position}) must be in range "
            f"[0, {disk_size - 1}]"
        )

    if direction not in ("left", "right"):
        raise ValueError(
            f"direction must be 'left' or 'right', got '{direction}'"
        )


def _empty_analysis_result(
    head_position: int,
    disk_size: int,
    direction: str,
) -> Dict[str, Any]:
    """Build a result dict for an empty request queue."""
    empty = {
        "algorithm": "PLACEHOLDER",
        "initial_head": head_position,
        "request_order": [],
        "total_head_movement": 0,
        "average_seek_distance": 0.0,
        "steps": [],
    }
    fcfs_e = dict(empty, algorithm="FCFS")
    sstf_e = dict(empty, algorithm="SSTF")
    scan_e = dict(empty, algorithm="SCAN", direction=direction)
    cscan_e = dict(empty, algorithm="C-SCAN", direction=direction)

    return {
        "request_count": 0,
        "disk_size": disk_size,
        "head_position": head_position,
        "direction": direction,
        "results": {
            "FCFS": fcfs_e,
            "SSTF": sstf_e,
            "SCAN": scan_e,
            "C-SCAN": cscan_e,
        },
        "total_head_movements": {
            "FCFS": 0,
            "SSTF": 0,
            "SCAN": 0,
            "C-SCAN": 0,
        },
        "recommended_algorithm": "FCFS",
        "reason": (
            "No requests to schedule. FCFS selected as default "
            "(all algorithms produce zero head movement)."
        ),
    }
