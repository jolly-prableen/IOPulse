"""Scheduling integration utilities for OS Sentinel.

This module provides a single interface for selecting and running the scheduling
algorithms implemented in the project. It also builds the execution sequence and
creates a Gantt chart dynamically from the actual scheduling results.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .fcfs import fcfs_schedule
from .priority import priority_schedule
from .round_robin import round_robin_schedule
from .sjf import sjf_schedule


def _normalize_algorithm_name(name: str) -> str:
    """Normalize schedule names so the user can pass common aliases."""
    normalized = str(name).strip().lower().replace(" ", "_")
    aliases = {
        "fcfs": "fcfs",
        "sjf": "sjf",
        "priority": "priority",
        "priority_scheduling": "priority",
        "round_robin": "round_robin",
        "rr": "round_robin",
    }
    return aliases.get(normalized, normalized)


def _execution_sequence_from_schedule(schedule: List[Dict[str, Any]]) -> List[str]:
    """Build a simple execution order from a non-RR schedule result."""
    return [entry["pid"] for entry in schedule]


def _rr_segments(processes: Iterable[Dict[str, Any]], time_quantum: float) -> List[Dict[str, Any]]:
    """Generate RR time segments from the input processes for Gantt-chart plotting."""
    process_list = list(processes)
    arrival_order = sorted(process_list, key=lambda p: (p["arrival_time"], p["pid"]))
    remaining = {str(p["pid"]): float(p["burst_time"]) for p in process_list}
    ready_queue: deque[str] = deque()
    current_time = 0.0
    segments: List[Dict[str, Any]] = []
    finished: set[str] = set()

    while len(finished) < len(process_list):
        for process in arrival_order:
            pid = str(process["pid"])
            if (
                float(process["arrival_time"]) <= current_time
                and remaining[pid] > 0
                and pid not in finished
                and pid not in ready_queue
            ):
                ready_queue.append(pid)

        if not ready_queue:
            next_arrival = min(
                (p for p in arrival_order if str(p["pid"]) not in finished and remaining[str(p["pid"])] > 0),
                key=lambda p: float(p["arrival_time"]),
            )
            current_time = float(next_arrival["arrival_time"])
            continue

        pid = ready_queue.popleft()
        quantum_slice = min(float(time_quantum), remaining[pid])
        start_time = current_time
        current_time += quantum_slice
        segments.append({"pid": pid, "start": start_time, "end": current_time})
        remaining[pid] -= quantum_slice

        if remaining[pid] > 0:
            ready_queue.append(pid)
        else:
            finished.add(pid)

    return segments


def _gantt_segments_for_result(
    algorithm: str,
    processes: Iterable[Dict[str, Any]],
    result: Dict[str, Any],
    time_quantum: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Return the execution segments used to draw the Gantt chart."""
    if algorithm in {"fcfs", "sjf", "priority"}:
        segments = []
        for entry in result.get("schedule", []):
            start = float(entry.get("completion_time", 0.0)) - float(entry.get("burst_time", 0.0))
            end = float(entry.get("completion_time", 0.0))
            segments.append({"pid": str(entry["pid"]), "start": start, "end": end})
        return segments

    if algorithm == "round_robin":
        quantum = time_quantum if time_quantum is not None else result.get("time_quantum")
        if quantum is None:
            raise ValueError("Round Robin requires a time quantum for Gantt chart generation.")
        return _rr_segments(list(processes), float(quantum))

    raise ValueError(f"Unsupported scheduling algorithm: {algorithm}")


def schedule_processes(
    algorithm: str,
    processes: Iterable[Dict[str, Any]],
    time_quantum: Optional[float] = None,
) -> Dict[str, Any]:
    """Run the selected scheduling algorithm and enrich the result with sequence and chart data."""
    normalized_algorithm = _normalize_algorithm_name(algorithm)
    process_list = list(processes)

    if normalized_algorithm == "fcfs":
        result = fcfs_schedule(process_list)
    elif normalized_algorithm == "sjf":
        result = sjf_schedule(process_list)
    elif normalized_algorithm == "priority":
        result = priority_schedule(process_list)
    elif normalized_algorithm == "round_robin":
        if time_quantum is None:
            raise ValueError("Round Robin requires a time quantum.")
        result = round_robin_schedule(process_list, float(time_quantum))
        result["time_quantum"] = float(time_quantum)
    else:
        raise ValueError(f"Unsupported scheduling algorithm: {algorithm}")

    result["algorithm"] = normalized_algorithm

    if normalized_algorithm in {"fcfs", "sjf", "priority"}:
        result["execution_sequence"] = _execution_sequence_from_schedule(result.get("schedule", []))
    else:
        result["execution_sequence"] = result.get("execution_sequence", [])

    result["gantt_segments"] = _gantt_segments_for_result(
        normalized_algorithm,
        process_list,
        result,
        time_quantum=time_quantum,
    )

    for entry in result.get("schedule", []):
        entry["start_time"] = float(entry.get("completion_time", 0.0)) - float(entry.get("burst_time", 0.0))

    return result


def generate_gantt_chart(
    result: Dict[str, Any],
    save_path: Optional[str] = None,
    show_plot: bool = False,
) -> Tuple[Any, Any, List[Dict[str, Any]]]:
    """Create and optionally save a Gantt chart from a scheduling result."""
    segments = result.get("gantt_segments", [])
    if not segments:
        raise ValueError("No Gantt segments available for this scheduling result.")

    fig, ax = plt.subplots(figsize=(10, 4))
    y_positions = {pid: index for index, pid in enumerate(sorted({segment["pid"] for segment in segments}))}

    for segment in segments:
        pid = str(segment["pid"])
        start = float(segment["start"])
        end = float(segment["end"])
        ax.barh(
            y_positions[pid],
            end - start,
            left=start,
            height=0.8,
            alpha=0.8,
            edgecolor="black",
            label=pid,
        )

    ax.set_yticks([y_positions[pid] for pid in sorted(y_positions, key=lambda value: y_positions[value])])
    ax.set_yticklabels(sorted(y_positions, key=lambda value: y_positions[value]))
    ax.set_xlabel("Time")
    ax.set_ylabel("Processes")
    ax.set_title(f"Gantt Chart - {result.get('algorithm', 'Scheduling')}")
    ax.invert_yaxis()
    ax.grid(axis="x", linestyle="--", alpha=0.5)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    if show_plot:
        plt.show()

    return fig, ax, segments


def build_visualization(
    algorithm: str,
    processes: Iterable[Dict[str, Any]],
    time_quantum: Optional[float] = None,
    save_path: Optional[str] = None,
    show_plot: bool = False,
) -> Dict[str, Any]:
    """Convenience function to run a scheduling algorithm and create its chart."""
    result = schedule_processes(algorithm, processes, time_quantum=time_quantum)
    fig, ax, segments = generate_gantt_chart(result, save_path=save_path, show_plot=show_plot)
    result["figure"] = fig
    result["axes"] = ax
    result["gantt_segments"] = segments
    return result


if __name__ == "__main__":
    sample_processes = [
        {"pid": "P1", "arrival_time": 0, "burst_time": 5},
        {"pid": "P2", "arrival_time": 1, "burst_time": 3},
        {"pid": "P3", "arrival_time": 2, "burst_time": 2},
    ]
    result = schedule_processes("round_robin", sample_processes, time_quantum=2)
    print(result["execution_sequence"])
    print(result["average_waiting_time"])
    generate_gantt_chart(result, save_path="gantt_chart.png")
    print("Gantt chart saved to gantt_chart.png")
