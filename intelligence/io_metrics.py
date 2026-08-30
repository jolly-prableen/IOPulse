"""Process-level I/O telemetry for IOPulse.

This module extends the existing process monitoring system by collecting
per-process disk I/O counters from psutil and computing interval-based
rates from the cumulative counters that the OS maintains.

=== OS CONCEPT ===
Operating systems maintain cumulative I/O counters for each process. On
Linux these live under /proc/[pid]/io and on Windows they are exposed
through the NT kernel's per-process I/O tracking.  psutil abstracts this
across platforms via Process.io_counters(), which returns:

  - read_count    – number of read operations
  - write_count   – number of write operations
  - read_bytes    – total bytes read
  - write_bytes   – total bytes written

These counters are cumulative (monotonically non-decreasing) over the
lifetime of the process.  To derive useful metrics like bytes/sec we must
take the difference between two observations and divide by the elapsed
wall-clock time between them.

=== DESIGN ===
The collector stores the previous observation for each PID and computes
rates on the next observation.  This is intentionally decoupled from
psutil: public functions accept optional process objects for testability
and return plain dictionaries for easy serialization and dashboard
consumption.

Error handling follows the same pattern as the existing process monitor:
every per-process psutil call is wrapped to gracefully handle processes
that become inaccessible, terminate, or deny permission between listing
and reading.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from datetime import datetime, timezone
from math import isinf, isnan
from typing import Any, Dict, List, Optional, Tuple

import psutil


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


def _safe_int(value: Any, default: int = 0) -> int:
    """Return value as int or default when the input is invalid."""
    if value is None:
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _iso_timestamp() -> str:
    """Return a UTC ISO 8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _compute_rates(
    prev_read_bytes: int,
    prev_write_bytes: int,
    curr_read_bytes: int,
    curr_write_bytes: int,
    elapsed: float,
) -> Tuple[float, float, float, float]:
    """Compute I/O rates and read/write ratio from cumulative counters.

    All inputs must be non-negative.  Returns:
        (read_bytes_per_sec, write_bytes_per_sec, total_io_bytes_per_sec,
         read_write_ratio)

    Edge cases:
        - elapsed <= 0  → rates are 0.0 (division by zero guarded)
        - total == 0    → ratio is 0.0 (no I/O to compare)
        - write == 0 and read > 0  → ratio is float('inf') clamped to
          a large sentinel value so the dict stays JSON-serializable.
    """
    if elapsed <= 0:
        return (0.0, 0.0, 0.0, 0.0)

    delta_read = max(0, curr_read_bytes - prev_read_bytes)
    delta_write = max(0, curr_write_bytes - prev_write_bytes)

    read_bytes_per_sec = delta_read / elapsed
    write_bytes_per_sec = delta_write / elapsed
    total_io_bytes_per_sec = read_bytes_per_sec + write_bytes_per_sec

    if total_io_bytes_per_sec == 0:
        read_write_ratio = 0.0
    elif write_bytes_per_sec == 0:
        read_write_ratio = float("inf")
    else:
        read_write_ratio = read_bytes_per_sec / write_bytes_per_sec

    return (read_bytes_per_sec, write_bytes_per_sec, total_io_bytes_per_sec, read_write_ratio)


# ---------------------------------------------------------------------------
# Single-process I/O collection
# ---------------------------------------------------------------------------

def collect_process_io(process: psutil.Process) -> Optional[Dict[str, Any]]:
    """Read I/O counters for a single process.

    Returns a dictionary of cumulative I/O counters or None when the
    counters are not accessible.  This function does NOT compute rates;
    use ``ProcessIOCollector`` for interval-based rate metrics.

    Returned dict keys:
        pid, name, state, read_bytes, write_bytes, read_count, write_count
    """
    try:
        with process.oneshot():
            pid = process.pid
            name = process.name() or "unknown"

            try:
                status = process.status()
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                status = "unknown"

            try:
                io = process.io_counters()
                read_bytes = _safe_int(getattr(io, "read_bytes", None))
                write_bytes = _safe_int(getattr(io, "write_bytes", None))
                read_count = _safe_int(getattr(io, "read_count", None))
                write_count = _safe_int(getattr(io, "write_count", None))
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                return None
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return None
    except Exception:
        return None

    if pid is None:
        return None

    return {
        "pid": int(pid),
        "name": str(name).strip() or "unknown",
        "state": str(status).strip() if status else "unknown",
        "read_bytes": read_bytes,
        "write_bytes": write_bytes,
        "read_count": read_count,
        "write_count": write_count,
    }


# ---------------------------------------------------------------------------
# Collector with interval-based rate computation
# ---------------------------------------------------------------------------

class ProcessIOCollector:
    """Stateful collector that computes per-process I/O rates.

    The collector stores the most recent cumulative counters for each PID
    and computes bytes/sec rates when the next observation arrives.  This
    mirrors how the existing ``ProcessAnomalyDetector`` maintains bounded
    per-process state.

    Usage::

        collector = ProcessIOCollector()
        # ... at each observation interval ...
        metrics = collector.collect_all()
    """

    def __init__(self, history_limit: int = 60) -> None:
        """Initialise the collector.

        Args:
            history_limit: maximum number of per-process rate snapshots to
                retain in the bounded history ring.  Keeps memory bounded
                like the existing anomaly detector.
        """
        self.history_limit = max(1, int(history_limit))
        self._prev: Dict[int, Dict[str, Any]] = OrderedDict()
        self._prev_timestamp: Dict[int, float] = {}
        self._history: Dict[int, List[Dict[str, Any]]] = {}

    def _compute_and_record(
        self,
        pid: int,
        name: str,
        state: str,
        read_bytes: int,
        write_bytes: int,
        read_count: int,
        write_count: int,
        cpu_percent: float,
        memory_percent: float,
    ) -> Optional[Dict[str, Any]]:
        """Compute rates for *pid* using stored previous observation.

        Returns a full ProcessIOMetrics dict or None if this is the first
        observation (no previous data to delta against).
        """
        now = time.time()
        prev = self._prev.get(pid)

        # First observation for this PID – store and return without rates.
        if prev is None:
            self._prev[pid] = {
                "read_bytes": read_bytes,
                "write_bytes": write_bytes,
                "read_count": read_count,
                "write_count": write_count,
            }
            self._prev_timestamp[pid] = now
            return None

        prev_time = self._prev_timestamp.get(pid, now)
        elapsed = now - prev_time

        read_bps, write_bps, total_bps, rw_ratio = _compute_rates(
            prev_read_bytes=prev["read_bytes"],
            prev_write_bytes=prev["write_bytes"],
            curr_read_bytes=read_bytes,
            curr_write_bytes=write_bytes,
            elapsed=elapsed,
        )

        # Update stored state for the next interval.
        self._prev[pid] = {
            "read_bytes": read_bytes,
            "write_bytes": write_bytes,
            "read_count": read_count,
            "write_count": write_count,
        }
        self._prev_timestamp[pid] = now

        metrics = {
            "pid": pid,
            "name": name,
            "state": state,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "read_bytes": read_bytes,
            "write_bytes": write_bytes,
            "read_count": read_count,
            "write_count": write_count,
            "read_bytes_per_sec": round(read_bps, 2),
            "write_bytes_per_sec": round(write_bps, 2),
            "total_io_bytes_per_sec": round(total_bps, 2),
            "read_write_ratio": round(rw_ratio, 4) if rw_ratio != float("inf") else float("inf"),
            "timestamp": now,
        }

        # Bounded per-process history.
        history = self._history.setdefault(pid, [])
        history.append(metrics)
        if len(history) > self.history_limit:
            history.pop(0)

        return metrics

    def collect_single(
        self,
        process: psutil.Process,
        cpu_percent: float = 0.0,
        memory_percent: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        """Collect I/O metrics for a single process.

        Reads cumulative I/O counters, computes rates against the previous
        observation (if any), and stores the new state.

        Returns a full metrics dict (with rates) or None when:
            - This is the first observation for this PID (no rates yet)
            - I/O counters are not accessible
            - The process terminated or denied access
        """
        raw = collect_process_io(process)
        if raw is None:
            return None

        return self._compute_and_record(
            pid=raw["pid"],
            name=raw["name"],
            state=raw["state"],
            read_bytes=raw["read_bytes"],
            write_bytes=raw["write_bytes"],
            read_count=raw["read_count"],
            write_count=raw["write_count"],
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
        )

    def collect_all(
        self,
        cpu_percent_map: Optional[Dict[int, float]] = None,
        memory_percent_map: Optional[Dict[int, float]] = None,
    ) -> List[Dict[str, Any]]:
        """Collect I/O metrics for all accessible processes.

        Iterates every running process, reads I/O counters, and computes
        rates.  Processes that are inaccessible or have no I/O counters
        are silently skipped.

        Args:
            cpu_percent_map: optional dict mapping PID → CPU% to attach
                to the metrics.  Useful when the caller already has fresh
                CPU readings.
            memory_percent_map: optional dict mapping PID → MEM%.

        Returns a list of metrics dicts (only processes where rates could
        be computed, i.e., those with at least one prior observation).
        """
        cpu_map = cpu_percent_map or {}
        mem_map = memory_percent_map or {}
        results: List[Dict[str, Any]] = []

        for proc in psutil.process_iter(attrs=None):
            try:
                with proc.oneshot():
                    pid = proc.pid

                    try:
                        name = proc.name() or "unknown"
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        name = "unknown"

                    try:
                        status = proc.status()
                    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                        status = "unknown"

                    try:
                        cpu = float(proc.cpu_percent(interval=None))
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        cpu = 0.0

                    try:
                        mem = float(proc.memory_percent())
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        mem = 0.0

                    try:
                        io = proc.io_counters()
                        read_bytes = _safe_int(getattr(io, "read_bytes", None))
                        write_bytes = _safe_int(getattr(io, "write_bytes", None))
                        read_count = _safe_int(getattr(io, "read_count", None))
                        write_count = _safe_int(getattr(io, "write_count", None))
                    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                        continue
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            except Exception:
                continue

            if pid is None:
                continue

            cpu_val = cpu_map.get(pid, cpu)
            mem_val = mem_map.get(pid, mem)

            metrics = self._compute_and_record(
                pid=pid,
                name=str(name).strip() or "unknown",
                state=str(status).strip() if status else "unknown",
                read_bytes=read_bytes,
                write_bytes=write_bytes,
                read_count=read_count,
                write_count=write_count,
                cpu_percent=cpu_val,
                memory_percent=mem_val,
            )

            if metrics is not None:
                results.append(metrics)

        results.sort(key=lambda item: item.get("total_io_bytes_per_sec", 0.0), reverse=True)
        return results

    def get_process_history(self, pid: int) -> List[Dict[str, Any]]:
        """Return the bounded rate history for a specific PID."""
        return list(self._history.get(pid, []))

    def clear(self) -> None:
        """Reset all stored state."""
        self._prev.clear()
        self._prev_timestamp.clear()
        self._history.clear()
