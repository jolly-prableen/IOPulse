"""Round Robin CPU scheduling.

Round Robin uses a fixed time quantum and a ready queue. Each process runs for
at most the quantum, then it is placed back in the queue if it still has work
remaining. This implementation keeps the logic explicit and easy to explain in
an OS viva.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass
class Process:
    """Represents a process in the Round Robin simulation."""

    pid: str
    arrival_time: float
    burst_time: float


def _normalize_processes(
    processes: Iterable[Dict[str, Any] | Process],
) -> List[Process]:
    """Convert input values to a consistent Process list."""
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


def round_robin_schedule(
    processes: Iterable[Dict[str, Any] | Process],
    time_quantum: float,
) -> Dict[str, Any]:
    """Run a Round Robin simulation and return schedule metrics.

    The algorithm maintains a ready queue. Newly arrived processes are added to
    the back of the queue, and each process receives up to one time quantum before
    being requeued if more work remains.
    """
    if time_quantum <= 0:
        raise ValueError("Time quantum must be greater than zero.")

    process_list = _normalize_processes(processes)
    if not process_list:
        return {
            "schedule": [],
            "execution_sequence": [],
            "average_turnaround_time": 0.0,
            "average_waiting_time": 0.0,
        }

    arrival_order = sorted(process_list, key=lambda p: (p.arrival_time, p.pid))
    remaining_burst = {process.pid: process.burst_time for process in process_list}
    ready_queue: deque[str] = deque()
    completed: Dict[str, float] = {}
    execution_sequence: List[str] = []
    current_time = 0.0

    while len(completed) < len(process_list):
        for process in arrival_order:
            if (
                process.arrival_time <= current_time
                and remaining_burst[process.pid] > 0
                and process.pid not in completed
                and process.pid not in ready_queue
            ):
                ready_queue.append(process.pid)

        if not ready_queue:
            next_process = min(
                (process for process in arrival_order if remaining_burst[process.pid] > 0 and process.pid not in completed),
                key=lambda process: process.arrival_time,
            )
            current_time = next_process.arrival_time
            continue

        pid = ready_queue.popleft()
        process = next(item for item in process_list if item.pid == pid)
        quantum_slice = min(time_quantum, remaining_burst[pid])
        remaining_burst[pid] -= quantum_slice
        current_time += quantum_slice
        execution_sequence.append(pid)

        for future_process in arrival_order:
            if (
                future_process.arrival_time <= current_time
                and remaining_burst[future_process.pid] > 0
                and future_process.pid not in completed
                and future_process.pid not in ready_queue
                and future_process.pid != pid
            ):
                ready_queue.append(future_process.pid)

        if remaining_burst[pid] > 0:
            ready_queue.append(pid)
        else:
            completed[pid] = current_time

    schedule = []
    total_turnaround = 0.0
    total_waiting = 0.0

    for process in sorted(process_list, key=lambda p: (p.arrival_time, p.pid)):
        completion_time = completed[process.pid]
        turnaround_time = completion_time - process.arrival_time
        waiting_time = turnaround_time - process.burst_time
        schedule.append(
            {
                "pid": process.pid,
                "arrival_time": process.arrival_time,
                "burst_time": process.burst_time,
                "completion_time": completion_time,
                "turnaround_time": turnaround_time,
                "waiting_time": waiting_time,
            }
        )
        total_turnaround += turnaround_time
        total_waiting += waiting_time

    process_count = len(schedule)
    average_turnaround = total_turnaround / process_count if process_count else 0.0
    average_waiting = total_waiting / process_count if process_count else 0.0

    return {
        "schedule": schedule,
        "execution_sequence": execution_sequence,
        "average_turnaround_time": average_turnaround,
        "average_waiting_time": average_waiting,
    }


if __name__ == "__main__":
    sample_processes = [
        {"pid": "P1", "arrival_time": 0, "burst_time": 5},
        {"pid": "P2", "arrival_time": 1, "burst_time": 3},
        {"pid": "P3", "arrival_time": 2, "burst_time": 2},
    ]

    result = round_robin_schedule(sample_processes, time_quantum=2)
    print("Round Robin Schedule")
    print("PID  Arrival  Burst  Completion  Turnaround  Waiting")
    for item in result["schedule"]:
        print(
            f"{item['pid']:>3}  {item['arrival_time']:>7.1f}  {item['burst_time']:>5.1f}  "
            f"{item['completion_time']:>10.1f}  {item['turnaround_time']:>10.1f}  {item['waiting_time']:>7.1f}"
        )

    print(f"Execution Sequence: {' -> '.join(result['execution_sequence'])}")
    print(f"Average Turnaround Time: {result['average_turnaround_time']:.2f}")
    print(f"Average Waiting Time: {result['average_waiting_time']:.2f}")
