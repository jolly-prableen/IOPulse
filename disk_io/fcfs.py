"""
io/fcfs.py – FCFS (First Come First Serve) Disk Scheduling Algorithm
OS Sentinel – Teammate B (Memory & I/O Subsystem)

=== OS CONCEPT: DISK SCHEDULING ===

When multiple processes request data from a hard disk, the disk controller
must decide the order in which to serve these requests.  The disk head
moves across the disk surface to read/write at the requested cylinder
(track) numbers.  The total distance the head moves is called the **total
head movement** (or total seek distance), and minimizing it reduces I/O
latency.

=== FCFS – First Come First Serve ===

The simplest disk scheduling algorithm.  Requests are served strictly in
the order they arrive — no reordering whatsoever.

Advantages:
  - Fair: every request is treated equally.
  - Simple to implement.

Disadvantages:
  - The head may zigzag across the disk, resulting in high total seek
    distance compared to smarter algorithms.

=== STRUCTURED OUTPUT ===

The function returns a dictionary:
    {
        "algorithm":            "FCFS",
        "initial_head":         int,
        "request_order":        list[int],
        "total_head_movement":  int,
        "average_seek_distance": float,
        "steps":                list[dict],
    }

Each step dict:
    {
        "from":     int,   # head position before this move
        "to":       int,   # head position after this move
        "distance": int,   # absolute distance of this move
    }

This format makes it trivial for a future dashboard to animate the
head sweeping across the disk.
"""

from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Input validation (shared convention for all disk scheduling modules)
# ---------------------------------------------------------------------------

def _validate_inputs(
    requests: List[int],
    initial_head: int,
    disk_size: int,
) -> None:
    """Validate common disk scheduling inputs.

    Raises:
        ValueError – if any input is invalid.
    """
    if disk_size <= 0:
        raise ValueError(
            f"disk_size must be positive, got {disk_size}"
        )

    if not (0 <= initial_head < disk_size):
        raise ValueError(
            f"initial_head ({initial_head}) must be in range "
            f"[0, {disk_size - 1}]"
        )

    for req in requests:
        if not (0 <= req < disk_size):
            raise ValueError(
                f"Request position {req} is outside valid range "
                f"[0, {disk_size - 1}]"
            )


# ---------------------------------------------------------------------------
# FCFS algorithm
# ---------------------------------------------------------------------------

def fcfs(
    requests: List[int],
    initial_head: int,
    disk_size: int,
) -> Dict[str, Any]:
    """Simulate the FCFS (First Come First Serve) disk scheduling algorithm.

    === ALGORITHM (simple explanation) ===
    Serve every request in the exact order it appears in the queue.
    The head moves from its current position to the next request, then
    to the next, and so on — no reordering.

    Parameters:
        requests     – List of disk cylinder/track positions to service.
        initial_head – Starting position of the disk head.
        disk_size    – Total number of cylinders (valid range: 0 .. disk_size-1).

    Returns:
        Structured result dict (see module docstring for format).
    """
    _validate_inputs(requests, initial_head, disk_size)

    # Handle empty request list gracefully.
    if not requests:
        return {
            "algorithm":            "FCFS",
            "initial_head":         initial_head,
            "request_order":        [],
            "total_head_movement":  0,
            "average_seek_distance": 0.0,
            "steps":                [],
        }

    steps: List[Dict[str, Any]] = []
    current_head = initial_head
    total_movement = 0

    for req in requests:
        distance = abs(req - current_head)
        steps.append({
            "from":     current_head,
            "to":       req,
            "distance": distance,
        })
        total_movement += distance
        current_head = req

    request_order = [s["to"] for s in steps]
    avg_seek = round(total_movement / len(requests), 4)

    return {
        "algorithm":            "FCFS",
        "initial_head":         initial_head,
        "request_order":        request_order,
        "total_head_movement":  total_movement,
        "average_seek_distance": avg_seek,
        "steps":                steps,
    }
