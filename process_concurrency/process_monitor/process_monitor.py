"""Real-time process monitor for OS Sentinel.

This module is intentionally limited to Phase 1 of the project: collecting
live process details, displaying them in a terminal table, and refreshing at a
regular interval.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from typing import Any, Dict, List, Optional

import psutil


def clear_terminal() -> None:
    """Clear the terminal display for a cleaner live monitor view."""
    try:
        os.system("clear")
    except Exception:
        pass


def get_process_priority(process: psutil.Process) -> Optional[int]:
    """Return the process priority or None if the value cannot be accessed."""
    try:
        return int(process.nice())
    except (
        AttributeError,
        psutil.AccessDenied,
        psutil.NoSuchProcess,
        psutil.ZombieProcess,
    ):
        return None
    except Exception:
        return None


def get_process_info(process: psutil.Process) -> Optional[Dict[str, Any]]:
    """Collect a single process snapshot into a safe dictionary.

    The function avoids crashing on common OS errors such as access denial,
    disappeared processes, or zombie states.
    """
    try:
        with process.oneshot():
            pid = process.pid
            name = process.name() or "unknown"
            cpu_percent = process.cpu_percent(interval=None)
            memory_percent = process.memory_percent()
            status = process.status() or "unknown"
            priority = get_process_priority(process)
    except (
        psutil.AccessDenied,
        psutil.NoSuchProcess,
        psutil.ZombieProcess,
    ):
        return None
    except Exception:
        return None

    if pid is None:
        return None

    return {
        "pid": int(pid),
        "name": str(name).strip() or "unknown",
        "cpu_percent": float(cpu_percent) if cpu_percent is not None else 0.0,
        "memory_percent": float(memory_percent) if memory_percent is not None else 0.0,
        "status": str(status).strip() or "unknown",
        "priority": int(priority) if priority is not None else None,
    }


def get_processes() -> List[Dict[str, Any]]:
    """Return a list of visible process entries assembled from psutil."""
    collected: List[Dict[str, Any]] = []

    for proc in psutil.process_iter(attrs=None):
        process_info = get_process_info(proc)
        if process_info is not None:
            collected.append(process_info)

    collected.sort(key=lambda item: item["pid"])
    return collected


def display_process_table(processes: List[Dict[str, Any]]) -> None:
    """Print the process table in a readable terminal format."""
    if not processes:
        print("No accessible processes found.")
        return

    header = f"{'PID':<10} {'NAME':<20} {'CPU%':>8} {'MEM%':>8} {'PRIORITY':>10} {'STATUS':<12}"
    divider = "-" * len(header)

    print(header)
    print(divider)

    for process in processes:
        pid = process["pid"]
        name = process["name"]
        cpu_percent = process["cpu_percent"]
        memory_percent = process["memory_percent"]
        priority = process["priority"]
        status = process["status"]

        priority_display = "N/A" if priority is None else str(priority)

        print(
            f"{pid:<10} {name:<20} {cpu_percent:>8.1f} {memory_percent:>8.1f} "
            f"{priority_display:>10} {status:<12}"
        )


def run_monitor(refresh_seconds: float = 1.0, limit: Optional[int] = None) -> None:
    """Run the process monitor until interrupted by Ctrl+C.

    Args:
        refresh_seconds: time between refreshes in seconds.
        limit: optional maximum number of refresh cycles.
    """
    stop_requested = False

    def handle_sigint(signum: int, frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, handle_sigint)

    print("==============================================================")
    print("                       OS SENTINEL")
    print("                    PROCESS MONITOR")
    print("==============================================================")

    iteration = 0
    try:
        while not stop_requested:
            clear_terminal()
            print("==============================================================")
            print("                       OS SENTINEL")
            print("                    PROCESS MONITOR")
            print("==============================================================")
            display_process_table(get_processes())
            iteration += 1

            if limit is not None and iteration >= limit:
                break

            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        stop_requested = True
    finally:
        print("\nMonitor stopped cleanly.")


def build_parser() -> argparse.ArgumentParser:
    """Create a small CLI parser for the phase 1 monitor."""
    parser = argparse.ArgumentParser(description="Real-time OS Sentinel process monitor")
    parser.add_argument(
        "--refresh",
        type=float,
        default=1.0,
        help="Seconds between process refreshes (default: 1.0).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional number of refresh cycles before exiting.",
    )
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    try:
        run_monitor(refresh_seconds=args.refresh, limit=args.limit)
    except KeyboardInterrupt:
        print("\nMonitor stopped by user.")
        sys.exit(0)
