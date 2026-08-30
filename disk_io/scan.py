"""
io/scan.py – SCAN (Elevator) Disk Scheduling Algorithm
IOPulse – Memory & I/O Subsystem

=== SCAN – Elevator Algorithm ===

Named after an elevator: the disk head moves in one direction, servicing
all requests it encounters, until it reaches the **disk boundary**, then
reverses direction and services the remaining requests.

=== BOUNDARY CONVENTION ===

When the head reaches the end of the disk in the current direction, it
travels all the way to the **boundary** of the disk:

  - direction="right" → head goes to cylinder (disk_size - 1), then reverses.
  - direction="left"  → head goes to cylinder 0, then reverses.

The boundary itself is included in the head movement (the head physically
reaches it) but is NOT listed as a "serviced request" unless there is an
actual request at that cylinder.  However, the boundary visit IS recorded
as a step so the dashboard can animate the sweep correctly.

This is the standard textbook SCAN convention and ensures consistent,
deterministic results.

=== STRUCTURED OUTPUT ===

Same format as FCFS (see io/fcfs.py module docstring), with the addition
of:
    "direction": str   # "left" or "right" — the initial direction

The step for the boundary visit (if no request exists there) has the
same structure but represents the head reaching the edge before reversing.
"""

from typing import Any, Dict, List

from disk_io.fcfs import _validate_inputs


# ---------------------------------------------------------------------------
# Direction validation
# ---------------------------------------------------------------------------

def _validate_direction(direction: str) -> None:
    """Ensure direction is 'left' or 'right'.

    Raises:
        ValueError – if direction is invalid.
    """
    if direction not in ("left", "right"):
        raise ValueError(
            f"direction must be 'left' or 'right', got '{direction}'"
        )


# ---------------------------------------------------------------------------
# SCAN algorithm
# ---------------------------------------------------------------------------

def scan(
    requests: List[int],
    initial_head: int,
    disk_size: int,
    direction: str = "right",
) -> Dict[str, Any]:
    """Simulate the SCAN (Elevator) disk scheduling algorithm.

    === ALGORITHM (simple explanation) ===
    1. Sort the requests.
    2. Starting from `initial_head`, move in `direction`.
    3. Service every request encountered along the way.
    4. When you hit the disk boundary, reverse direction.
    5. Service the remaining requests on the way back.

    === BOUNDARY BEHAVIOR ===
    The head always travels to the disk boundary (0 or disk_size-1) before
    reversing, even if no request exists there.  This is the standard
    textbook SCAN behavior.

    Parameters:
        requests     – List of disk cylinder/track positions to service.
        initial_head – Starting position of the disk head.
        disk_size    – Total number of cylinders (valid range: 0 .. disk_size-1).
        direction    – Initial sweep direction: "left" or "right".

    Returns:
        Structured result dict with an additional "direction" key.
    """
    _validate_inputs(requests, initial_head, disk_size)
    _validate_direction(direction)

    # Handle empty request list gracefully.
    if not requests:
        return {
            "algorithm":            "SCAN",
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

        # Go to the right boundary if we're not already there.
        boundary = disk_size - 1
        if current_head != boundary:
            _move_to(boundary)

        # ---- Phase 2: reverse, sweep left ----
        for req in reversed(left):
            _move_to(req)

    else:  # direction == "left"
        # ---- Phase 1: sweep left toward 0 ----
        for req in reversed(left):
            _move_to(req)

        # Go to the left boundary if we're not already there.
        if current_head != 0:
            _move_to(0)

        # ---- Phase 2: reverse, sweep right ----
        for req in right:
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
        "algorithm":            "SCAN",
        "initial_head":         initial_head,
        "direction":            direction,
        "request_order":        request_order,
        "total_head_movement":  total_movement,
        "average_seek_distance": avg_seek,
        "steps":                steps,
    }
