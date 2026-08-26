"""Explainable process anomaly detection for OS Sentinel.

This module intentionally avoids machine learning. It uses a small set of
configurable rules based on recent observations from psutil and a bounded
history queue. The goal is to provide transparent alerts that are easy to
understand and easy to tune without depending on hidden statistical models.

CPU runaway detection:
    A process is considered potentially runaway when CPU usage stays above the
    configured threshold for the configured number of consecutive observations.
    This requirement is intentionally strict to avoid false positives from a
    single noisy sample.

CPU starvation heuristic:
    This is not a proof that the OS scheduler is starving a process. Instead,
    it is a conservative heuristic: a process that remains active in recent
    observations but receives extremely low CPU time for a sustained period may
    be worth investigating. The code uses only values available from psutil and
    never claims a definitive starvation condition.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Deque, Dict, Iterable, List, Optional, Sequence

CPU_THRESHOLD = 90.0
CONSECUTIVE_HIGH_CPU = 5
HISTORY_LIMIT = 100
STARVATION_CPU_THRESHOLD = 5.0
STARVATION_OBSERVATIONS = 15
STARVATION_CPU_TIME_DELTA = 0.5
STARVATION_MIN_CPU_TIME_DELTA = 0.05
STARVATION_ACTIVE_CPU_PERCENT = 0.1


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Return value as float or default when the input is invalid."""
    if value is None:
        return default

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return default

    if not isfinite(numeric_value):
        return default

    return numeric_value


def _safe_str(value: Any, default: str = "unknown") -> str:
    """Coerce a value to a readable string without crashing."""
    if value is None:
        return default

    text = str(value).strip()
    return text if text else default


def _iso_timestamp() -> str:
    """Return a UTC ISO 8601 timestamp for new alert entries."""
    return datetime.now(timezone.utc).isoformat()


def make_observation(
    pid: Any,
    name: str = "python",
    cpu_percent: float = 0.0,
    status: str = "running",
    timestamp: Optional[str] = None,
    cpu_time: float = 0.0,
) -> Dict[str, Any]:
    """Create a normalized observation dictionary for testing and reuse."""
    return {
        "pid": pid,
        "name": name,
        "cpu_percent": cpu_percent,
        "status": status,
        "timestamp": timestamp or _iso_timestamp(),
        "cpu_times": {"user": cpu_time, "system": 0.0},
    }


class ProcessAnomalyDetector:
    """Track recent process observations and emit explainable alerts.

    The detector intentionally uses simple threshold-based logic, not model-based
    anomaly detection. It records a bounded per-process history and keeps a
    cumulative counter of consecutive high-CPU observations to prevent false
    positives from a single spike.
    """

    def __init__(
        self,
        cpu_threshold: float = CPU_THRESHOLD,
        consecutive_high_cpu: int = CONSECUTIVE_HIGH_CPU,
        history_limit: int = HISTORY_LIMIT,
        starvation_cpu_threshold: float = STARVATION_CPU_THRESHOLD,
        starvation_observations: int = STARVATION_OBSERVATIONS,
        starvation_cpu_time_delta: float = STARVATION_CPU_TIME_DELTA,
        starvation_min_cpu_time_delta: float = STARVATION_MIN_CPU_TIME_DELTA,
    ) -> None:
        self.cpu_threshold = float(cpu_threshold)
        self.consecutive_high_cpu = int(consecutive_high_cpu)
        self.history_limit = max(1, int(history_limit))
        self.starvation_cpu_threshold = float(starvation_cpu_threshold)
        self.starvation_observations = max(1, int(starvation_observations))
        self.starvation_cpu_time_delta = float(starvation_cpu_time_delta)
        self.starvation_min_cpu_time_delta = max(0.0, float(starvation_min_cpu_time_delta))

        self.history: Dict[int, Deque[Dict[str, Any]]] = defaultdict(deque)
        self.consecutive_high_cpu_count: Dict[int, int] = {}
        self.starvation_alerted: set[int] = set()

    def _build_alert(
        self,
        pid: int,
        name: str,
        category: str,
        message: str,
        severity: str,
        observed_value: Any,
        threshold: Optional[float] = None,
        status: Optional[str] = None,
        timestamp: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Create a structured alert payload with common metadata."""
        alert = {
            "timestamp": timestamp or _iso_timestamp(),
            "severity": severity,
            "category": category,
            "pid": int(pid),
            "process_name": _safe_str(name, "unknown"),
            "name": _safe_str(name, "unknown"),
            "message": message,
            "observed_value": observed_value,
            "threshold": threshold,
            "status": _safe_str(status, "unknown") if status is not None else None,
        }
        alert.update(extra)
        return alert

    def _record_history(self, pid: int, observation: Dict[str, Any]) -> None:
        """Append a normalized observation, keeping the per-process history bounded."""
        queue = self.history.get(pid)
        if queue is None:
            queue = deque(maxlen=self.history_limit)
            self.history[pid] = queue

        queue.append(observation)
        if len(queue) > self.history_limit:
            queue.popleft()

    def _detect_runaway(self, pid: int, name: str, cpu_percent: float, status: str, timestamp: str) -> List[Dict[str, Any]]:
        """Warn when CPU is repeatedly above the configured threshold."""
        if cpu_percent >= self.cpu_threshold:
            count = self.consecutive_high_cpu_count.get(pid, 0) + 1
            self.consecutive_high_cpu_count[pid] = count
        else:
            self.consecutive_high_cpu_count[pid] = 0
            return []

        if count < self.consecutive_high_cpu:
            return []

        return [
            self._build_alert(
                pid=pid,
                name=name,
                category="runaway_process",
                message="WARNING Possible runaway process detected.",
                severity="WARNING",
                observed_value=cpu_percent,
                threshold=self.cpu_threshold,
                status=status,
                timestamp=timestamp,
                consecutive_observations=count,
            )
        ]

    def _detect_zombie(self, pid: int, name: str, status: str, timestamp: str) -> List[Dict[str, Any]]:
        """Warn when a process is marked as zombie."""
        normalized_status = str(status).lower()
        if normalized_status != "zombie":
            return []

        return [
            self._build_alert(
                pid=pid,
                name=name,
                category="zombie_process",
                message="WARNING Zombie process detected.",
                severity="WARNING",
                observed_value=status,
                threshold=None,
                status=status,
                timestamp=timestamp,
            )
        ]

    def _detect_starvation(self, pid: int, name: str, status: str, timestamp: str) -> List[Dict[str, Any]]:
        """Heuristic for possible CPU starvation.

        This is intentionally conservative and explainable: if a process remains
        continuously present in recent observations and receives extremely low
        CPU over a sustained period, the detector raises a WARNING. It does not
        claim that starvation definitely exists; instead, it highlights a process
        worthy of investigation.
        """
        history = list(self.history.get(pid, []))
        if len(history) < self.starvation_observations:
            if pid in self.starvation_alerted:
                self.starvation_alerted.discard(pid)
            return []

        recent = history[-self.starvation_observations :]
        cpu_values = []
        cpu_time_values = []
        statuses = []

        for item in recent:
            cpu_value = _safe_float(item.get("cpu_percent"))
            if cpu_value is None:
                continue
            cpu_values.append(cpu_value)
            statuses.append(str(item.get("status", "")).lower())

            cpu_times = item.get("cpu_times") or {}
            user_cpu = _safe_float(cpu_times.get("user"))
            system_cpu = _safe_float(cpu_times.get("system"))
            if user_cpu is None or system_cpu is None:
                continue
            cpu_time_values.append(user_cpu + system_cpu)

        if (
            len(cpu_values) < self.starvation_observations
            or len(cpu_time_values) < self.starvation_observations
        ):
            if pid in self.starvation_alerted:
                self.starvation_alerted.discard(pid)
            return []

        average_cpu = sum(cpu_values) / len(cpu_values)
        cpu_time_delta = cpu_time_values[-1] - cpu_time_values[0]
        cpu_time_is_monotonic = all(
            current >= previous for previous, current in zip(cpu_time_values, cpu_time_values[1:])
        )
        active_observations = sum(value > STARVATION_ACTIVE_CPU_PERCENT for value in cpu_values)
        normalized_status = str(status).lower()
        qualifies = (
            average_cpu <= self.starvation_cpu_threshold
            and normalized_status == "running"
            and all(item_status == "running" for item_status in statuses)
            and active_observations >= int(self.starvation_observations * 0.8)
            and cpu_time_is_monotonic
            and self.starvation_min_cpu_time_delta <= cpu_time_delta <= self.starvation_cpu_time_delta
        )

        if not qualifies:
            if pid in self.starvation_alerted:
                self.starvation_alerted.discard(pid)
            return []

        if pid in self.starvation_alerted:
            return []

        self.starvation_alerted.add(pid)
        return [
            self._build_alert(
                pid=pid,
                name=name,
                category="possible_cpu_starvation",
                message="Possible CPU starvation detected.",
                severity="WARNING",
                observed_value=average_cpu,
                threshold=self.starvation_cpu_threshold,
                status=status,
                timestamp=timestamp,
                window_size=self.starvation_observations,
            )
        ]

    def record_observation(self, observation: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Validate, store, and evaluate a single process observation.

        Returns a list of alert dictionaries. Invalid or incomplete observations
        are ignored rather than crashing the detector.
        """
        if not isinstance(observation, dict):
            return []

        try:
            pid_value = int(observation.get("pid"))
        except (TypeError, ValueError):
            return []

        if pid_value < 0:
            return []

        raw_name = observation.get("name")
        name = _safe_str(raw_name, "unknown")
        status = _safe_str(observation.get("status"), "unknown")
        timestamp = _safe_str(observation.get("timestamp"), _iso_timestamp())

        cpu_value = _safe_float(observation.get("cpu_percent"))
        if cpu_value is None:
            return []

        normalized = {
            "pid": pid_value,
            "name": name,
            "status": status,
            "timestamp": timestamp,
            "cpu_percent": float(cpu_value),
            "cpu_times": observation.get("cpu_times") or {},
        }

        self._record_history(pid_value, normalized)

        alerts: List[Dict[str, Any]] = []
        alerts.extend(self._detect_zombie(pid_value, name, status, timestamp))
        alerts.extend(self._detect_runaway(pid_value, name, float(cpu_value), status, timestamp))
        alerts.extend(self._detect_starvation(pid_value, name, status, timestamp))
        return alerts

    def detect_anomalies(self, observations: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process a batch of observations and return all alerts in order."""
        alerts: List[Dict[str, Any]] = []
        for observation in observations or []:
            alerts.extend(self.record_observation(observation))
        return alerts
