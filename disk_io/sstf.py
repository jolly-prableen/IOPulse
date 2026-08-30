"""
io/sstf.py – SSTF (Shortest Seek Time First) Disk Scheduling Algorithm
IOPulse – Memory & I/O Subsystem

=== SSTF – Shortest Seek Time First ===

At every step, the disk head moves to the **closest** unserved request.
This is a greedy algorithm: it always picks the request with the smallest
absolute distance from the current head position.

Advantages:
  - Significantly lower total head movement than FCFS.
  - Good throughput under moderate load.

Disadvantages:
  - May cause **starvation**: requests far from the current head may wait
    indefinitely if new requests keep arriving nearby.
  - Not as fair as FCFS.

When there is a tie (two requests at equal distance), we choose the one
with the **smaller cylinder number** for deterministic, testable behavior.

=== STRUCTURED OUTPUT ===

Same format as FCFS (see io/fcfs.py module docstring).
"""

from typing import Any, Dict, List

from disk_io.fcfs import _validate_inputs


# ---------------------------------------------------------------------------
# SSTF algorithm
# ---------------------------------------------------------------------------

def sstf(
    requests: List[int],
    initial_head: int,
    disk_size: int,
) -> Dict[str, Any]:
    """Simulate the SSTF (Shortest Seek Time First) disk scheduling algorithm.

    === ALGORITHM (simple explanation) ===
    1. Look at all unserved requests.
    2. Find the one closest to the current head position.
    3. Move the head there and mark it served.
    4. Repeat until every request has been served.

    Tie-breaking: if two requests are equidistant, the one with the
    smaller cylinder number is served first.

    Parameters:
        requests     – List of disk cylinder/track positions to service.
        initial_head – Starting position of the disk head.
        disk_size    – Total number of cylinders (valid range: 0 .. disk_size-1).

    Returns:
        Structured result dict (see io/fcfs.py module docstring for format).
    """
    _validate_inputs(requests, initial_head, disk_size)

    # Handle empty request list gracefully.
    if not requests:
        return {
            "algorithm":            "SSTF",
            "initial_head":         initial_head,
            "request_order":        [],
            "total_head_movement":  0,
            "average_seek_distance": 0.0,
            "steps":                [],
        }

    # Work on a copy so we don't mutate the caller's list.
    pending = list(requests)

    steps: List[Dict[str, Any]] = []
    current_head = initial_head
    total_movement = 0

    while pending:
        # Find the closest pending request.
        # Tie-break: smaller cylinder number first (stable, predictable).
        closest = min(pending, key=lambda r: (abs(r - current_head), r))

        distance = abs(closest - current_head)
        steps.append({
            "from":     current_head,
            "to":       closest,
            "distance": distance,
        })
        total_movement += distance
        current_head = closest

        # Remove ONE occurrence (handles duplicate requests correctly).
        pending.remove(closest)

    request_order = [s["to"] for s in steps]
    avg_seek = round(total_movement / len(requests), 4)

    return {
        "algorithm":            "SSTF",
        "initial_head":         initial_head,
        "request_order":        request_order,
        "total_head_movement":  total_movement,
        "average_seek_distance": avg_seek,
        "steps":                steps,
    }
