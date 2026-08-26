"""Non-preemptive Shortest Job First (SJF) CPU scheduling.

SJF chooses the available process with the shortest burst time. A process that
arrives later cannot be run before a currently ready shorter job, which is the
standard non-preemptive interpretation of SJF.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass
class Process:
    """Represents a process in the non-preemptive SJF simulation."""

    pid: str
    arrival_time: float
    burst_time: float


def _normalize_processes(
    processes: Iterable[Dict[str, Any] | Process],
) -> List[Process]:
    """Convert input values into a consistent list of Process objects."""
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


def sjf_schedule(processes: Iterable[Dict[str, Any] | Process]) -> Dict[str, Any]:
    """Run the non-preemptive SJF scheduling algorithm.

    The algorithm keeps a ready queue of processes whose arrival times are less
    than or equal to the current system time. It then chooses the process with the
    shortest burst time among ready jobs. If multiple processes have equal burst
    times, the process with the earlier arrival time is selected; ties are then
    broken by PID for deterministic ordering.
    """
    process_list = _normalize_processes(processes)
    if not process_list:
        return {
            "schedule": [],
            "average_turnaround_time": 0.0,
            "average_waiting_time": 0.0,
        }

    remaining = sorted(process_list, key=lambda p: (p.arrival_time, p.pid))
    current_time = 0.0
    schedule: List[Dict[str, Any]] = []
    total_turnaround = 0.0
    total_waiting = 0.0

    while remaining:
        ready = [process for process in remaining if process.arrival_time <= current_time]

        if not ready:
            next_arrival = min(process.arrival_time for process in remaining)
            current_time = next_arrival
            continue

        selected = min(
            ready,
            key=lambda process: (process.burst_time, process.arrival_time, process.pid),
        )

        remaining.remove(selected)
        start_time = current_time
        completion_time = current_time + selected.burst_time
        turnaround_time = completion_time - selected.arrival_time
        waiting_time = turnaround_time - selected.burst_time

        schedule.append(
            {
                "pid": selected.pid,
                "arrival_time": selected.arrival_time,
                "burst_time": selected.burst_time,
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
        {"pid": "P1", "arrival_time": 0, "burst_time": 7},
        {"pid": "P2", "arrival_time": 2, "burst_time": 4},
        {"pid": "P3", "arrival_time": 4, "burst_time": 1},
        {"pid": "P4", "arrival_time": 5, "burst_time": 3},
    ]

    result = sjf_schedule(sample_processes)
    print("SJF Schedule")
    print("PID  Arrival  Burst  Start  Completion  Turnaround  Waiting")
    for item in result["schedule"]:
        print(
            f"{item['pid']:>3}  {item['arrival_time']:>7.1f}  {item['burst_time']:>5.1f}  "
            f"{item['start_time']:>5.1f}  {item['completion_time']:>10.1f}  "
            f"{item['turnaround_time']:>10.1f}  {item['waiting_time']:>7.1f}"
        )

    print(f"Average Turnaround Time: {result['average_turnaround_time']:.2f}")
    print(f"Average Waiting Time: {result['average_waiting_time']:.2f}")
