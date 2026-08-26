"""First Come First Serve (FCFS) CPU scheduling.

FCFS is the simplest non-preemptive scheduling policy: processes are executed
in the order they arrive. This implementation is intentionally explicit and
readable so a student can explain the calculations during a viva.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Dict, Any


@dataclass
class Process:
    """Represents a process in the FCFS simulation."""

    pid: str
    arrival_time: float
    burst_time: float


def _normalize_processes(processes: Iterable[Dict[str, Any] | Process]) -> List[Process]:
    """Convert input data into a consistent list of Process objects."""
    normalized: List[Process] = []

    for item in processes:
        if isinstance(item, Process):
            normalized.append(item)
            continue

        if not isinstance(item, dict):
            raise TypeError("Each process must be a dict or a Process object.")

        required_keys = {"pid", "arrival_time", "burst_time"}
        missing = required_keys - set(item.keys())
        if missing:
            raise ValueError(f"Process is missing required keys: {sorted(missing)}")

        normalized.append(
            Process(
                pid=str(item["pid"]),
                arrival_time=float(item["arrival_time"]),
                burst_time=float(item["burst_time"]),
            )
        )

    return normalized


def fcfs_schedule(processes: Iterable[Dict[str, Any] | Process]) -> Dict[str, Any]:
    """Run the FCFS scheduling algorithm and return the calculated metrics.

    FCFS executes processes in order of arrival time. If two processes arrive at
    the same instant, the earlier one in the input is kept first to maintain a
    consistent, deterministic order.

    Returns a dictionary with:
        - schedule: list of process execution details
        - average_turnaround_time
        - average_waiting_time
    """
    process_list = _normalize_processes(processes)
    if not process_list:
        return {
            "schedule": [],
            "average_turnaround_time": 0.0,
            "average_waiting_time": 0.0,
        }

    ordered = sorted(process_list, key=lambda p: (p.arrival_time, p.pid))
    current_time = 0.0
    schedule: List[Dict[str, Any]] = []
    total_turnaround = 0.0
    total_waiting = 0.0

    for process in ordered:
        if process.arrival_time > current_time:
            current_time = process.arrival_time

        start_time = current_time
        completion_time = start_time + process.burst_time
        turnaround_time = completion_time - process.arrival_time
        waiting_time = turnaround_time - process.burst_time

        schedule.append(
            {
                "pid": process.pid,
                "arrival_time": process.arrival_time,
                "burst_time": process.burst_time,
                "start_time": start_time,
                "completion_time": completion_time,
                "turnaround_time": turnaround_time,
                "waiting_time": waiting_time,
            }
        )

        total_turnaround += turnaround_time
        total_waiting += waiting_time
        current_time = completion_time

    process_count = len(schedule)
    average_turnaround = total_turnaround / process_count if process_count else 0.0
    average_waiting = total_waiting / process_count if process_count else 0.0

    return {
        "schedule": schedule,
        "average_turnaround_time": average_turnaround,
        "average_waiting_time": average_waiting,
    }


if __name__ == "__main__":
    sample_processes = [
        {"pid": "P1", "arrival_time": 0, "burst_time": 5},
        {"pid": "P2", "arrival_time": 1, "burst_time": 3},
        {"pid": "P3", "arrival_time": 2, "burst_time": 2},
    ]

    result = fcfs_schedule(sample_processes)
    print("FCFS Schedule")
    print("PID  Arrival  Burst  Start  Completion  Turnaround  Waiting")
    for item in result["schedule"]:
        print(
            f"{item['pid']:>3}  {item['arrival_time']:>7.1f}  {item['burst_time']:>5.1f}  "
            f"{item['start_time']:>5.1f}  {item['completion_time']:>10.1f}  "
            f"{item['turnaround_time']:>10.1f}  {item['waiting_time']:>7.1f}"
        )

    print(f"Average Turnaround Time: {result['average_turnaround_time']:.2f}")
    print(f"Average Waiting Time: {result['average_waiting_time']:.2f}")
