"""
io/cscan.py – C-SCAN (Circular SCAN) Disk Scheduling Algorithm
OS Sentinel – Teammate B (Memory & I/O Subsystem)

=== C-SCAN – Circular SCAN ===

C-SCAN is a variant of SCAN that provides **more uniform wait times**.

=== KEY DIFFERENCE FROM SCAN ===

SCAN (Elevator):
  - Head sweeps in one direction, then REVERSES and services requests
    on the way back.  Requests near the middle of the disk get served
    more frequently (the head passes them on both sweeps).

C-SCAN (Circular SCAN):
  - Head sweeps in one direction ONLY.
  - When it reaches the disk boundary, it **jumps back** to the
    opposite boundary WITHOUT servicing any requests along the way.
  - Then it continues sweeping in the SAME direction.
  - This treats the disk as circular, giving all cylinders a more
    equal chance of being serviced.

=== BOUNDARY CONVENTION ===

When the head reaches the end of the disk in its sweep direction:
  1. It travels to the boundary (disk_size-1 or 0).
  2. It jumps to the opposite boundary (0 or disk_size-1).
     This jump is recorded as a step with its actual distance.
  3. It continues in the original direction, servicing remaining requests.

The boundary visits are recorded as steps for dashboard animation.

=== STRUCTURED OUTPUT ===

Same format as SCAN (see io/scan.py module docstring).
"""

from typing import Any, Dict, List

from disk_io.fcfs import _validate_inputs
from disk_io.scan import _validate_direction


# ---------------------------------------------------------------------------
# C-SCAN algorithm
# ---------------------------------------------------------------------------

def cscan(
    requests: List[int],
    initial_head: int,
    disk_size: int,
    direction: str = "right",
) -> Dict[str, Any]:
    """Simulate the C-SCAN (Circular SCAN) disk scheduling algorithm.

    === ALGORITHM (simple explanation) ===
    1. Sort the requests.
    2. Starting from `initial_head`, move in `direction`.
    3. Service every request encountered along the way.
    4. When you reach the disk boundary, jump to the opposite boundary.
    5. Continue in the SAME direction and service remaining requests.

    Unlike SCAN, the head does NOT reverse direction.  It always sweeps
    in one direction, jumps back, and sweeps in the same direction again.

    === BOUNDARY BEHAVIOR ===
    The head always travels to the disk boundary before jumping, and the
    jump goes to the opposite boundary.  Both are recorded as steps.

    Parameters:
        requests     – List of disk cylinder/track positions to service.
        initial_head – Starting position of the disk head.
        disk_size    – Total number of cylinders (valid range: 0 .. disk_size-1).
        direction    – Sweep direction: "left" or "right".

    Returns:
        Structured result dict with an additional "direction" key.
    """
    _validate_inputs(requests, initial_head, disk_size)
    _validate_direction(direction)

    # Handle empty request list gracefully.
    if not requests:
        return {
            "algorithm":            "C-SCAN",
            "initial_head":         initial_head,
            "direction":            direction,
            "request_order":        [],
            "total_head_movement":  0,
            "average_seek_distance": 0.0,
            "steps":                [],
        }

    # Split requests into those left of and right of (or equal to) the head.
    left  = sorted([r for r in requests if r < initial_head])
    right = sorted([r for r in requests if r >= initial_head])

    steps: List[Dict[str, Any]] = []
    current_head = initial_head
    total_movement = 0

    def _move_to(target: int) -> None:
        """Record a head movement to `target`."""
        nonlocal current_head, total_movement
        distance = abs(target - current_head)
        steps.append({
            "from":     current_head,
            "to":       target,
            "distance": distance,
        })
        total_movement += distance
        current_head = target

    if direction == "right":
        # ---- Phase 1: sweep right toward disk_size-1 ----
        for req in right:
            _move_to(req)

        # Go to the right boundary if we're not already there and
        # there are still requests on the left to service.
        if left:
            boundary_right = disk_size - 1
            if current_head != boundary_right:
                _move_to(boundary_right)

            # Jump to the left boundary (0).
            _move_to(0)

            # ---- Phase 2: sweep right again for remaining requests ----
            for req in left:
                _move_to(req)

    else:  # direction == "left"
        # ---- Phase 1: sweep left toward 0 ----
        for req in reversed(left):
            _move_to(req)

        # Go to the left boundary if we're not already there and
        # there are still requests on the right to service.
        if right:
            if current_head != 0:
                _move_to(0)

            # Jump to the right boundary (disk_size - 1).
            _move_to(disk_size - 1)

            # ---- Phase 2: sweep left again for remaining requests ----
            for req in reversed(right):
                _move_to(req)

    # Build request_order (filter out boundary-only steps).
    all_requests_set = list(requests)  # keep duplicates
    request_order = []
    for s in steps:
        target = s["to"]
        if target in all_requests_set:
            request_order.append(target)
            all_requests_set.remove(target)

    avg_seek = round(total_movement / len(requests), 4) if requests else 0.0

    return {
        "algorithm":            "C-SCAN",
        "initial_head":         initial_head,
        "direction":            direction,
        "request_order":        request_order,
        "total_head_movement":  total_movement,
        "average_seek_distance": avg_seek,
        "steps":                steps,
    }
