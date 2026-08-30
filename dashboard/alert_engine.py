from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Iterable, Optional


SEVERITIES = {"INFO", "WARNING", "CRITICAL"}


@dataclass(frozen=True)
class Alert:
    timestamp: str
    severity: str
    category: str
    message: str
    suggested_action: str
    pid: Optional[int] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "suggested_action": self.suggested_action,
            "pid": self.pid,
        }


class AlertEngine:
    """Normalize, retain, and deduplicate alerts from existing detectors."""

    _actions = {
        "runaway_process": "Investigate the process.",
        "zombie_process": "Investigate or clean up the zombie process.",
        "cpu_starvation": "Investigate CPU scheduling and process activity.",
        "deadlock": "Review the resource allocation graph.",
        "unsafe_state": "Review resource allocation and available resources.",
        "io_spike": "Investigate the process for unexpected I/O burst.",
        "io_stall": "Check if the process is hung or blocked on I/O.",
        "sustained_high_io": "Consider throttling the process or investigating workload.",
        "rw_ratio_shift": "Check if the process workload character has changed.",
        "io_classification_change": "Review the I/O behavior change for the process.",
    }
    _messages = {
        "runaway_process": "Possible runaway process detected.",
        "zombie_process": "Zombie process detected.",
        "cpu_starvation": "Possible CPU starvation detected.",
        "deadlock": "Potential deadlock detected.",
        "unsafe_state": "Unsafe resource-allocation state detected.",
        "io_spike": "I/O spike detected.",
        "io_stall": "I/O stall detected.",
        "sustained_high_io": "Sustained high I/O detected.",
        "rw_ratio_shift": "Read/write ratio shift detected.",
        "io_classification_change": "I/O classification changed.",
    }

    # Mapping from io_anomaly severity strings to alert engine SEVERITIES.
    _IO_SEVERITY_MAP = {
        "low": "INFO",
        "medium": "WARNING",
        "high": "CRITICAL",
        "critical": "CRITICAL",
    }

    def __init__(self, history_limit: int = 100, duplicate_window: float = 10.0) -> None:
        self.history_limit = max(1, int(history_limit))
        self.duplicate_window = max(0.0, float(duplicate_window))
        self._alerts: Deque[Alert] = deque(maxlen=self.history_limit)
        self._last_seen: Dict[tuple[str, Optional[int], str], datetime] = {}

    @property
    def alerts(self) -> list[Alert]:
        return list(self._alerts)

    @staticmethod
    def _timestamp(value: Any) -> str:
        if value is not None and str(value).strip():
            return str(value)
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _pid(value: Any) -> Optional[int]:
        try:
            return None if value is None or str(value).strip() == "" else int(value)
        except (TypeError, ValueError):
            return None

    def normalize(self, payload: Alert | Dict[str, Any]) -> Alert:
        """Convert detector or deadlock output into the common alert structure."""
        is_alert = isinstance(payload, Alert)
        data = payload.as_dict() if is_alert else dict(payload)
        category = str(data.get("category", "general"))
        if category == "possible_cpu_starvation":
            category = "cpu_starvation"

        if is_alert:
            severity = payload.severity
        else:
            severity = str(data.get("severity", "INFO")).upper()
            if category in {"deadlock", "unsafe_state"}:
                severity = "CRITICAL"
            elif category in self._actions:
                severity = "WARNING"
        if severity not in SEVERITIES:
            severity = "INFO"

        if is_alert:
            message = payload.message
        else:
            message = self._messages.get(category, str(data.get("message", "System alert.")))
            process_name = data.get("process_name", data.get("name"))
            details = []
            if process_name:
                details.append(f"process={process_name}")
            if data.get("observed_value") is not None:
                details.append(f"CPU={data['observed_value']}")
            if data.get("threshold") is not None:
                details.append(f"threshold={data['threshold']}")
            if data.get("consecutive_observations") is not None:
                details.append(f"consecutive={data['consecutive_observations']}")
            if details:
                message = f"{message} ({', '.join(details)})"

        return Alert(
            timestamp=self._timestamp(data.get("timestamp")),
            severity=severity,
            category=category,
            message=message,
            suggested_action=self._actions.get(category, str(data.get("suggested_action", "Investigate the alert."))),
            pid=self._pid(data.get("pid")),
        )

    def add(self, payload: Alert | Dict[str, Any]) -> Optional[Alert]:
        alert = self.normalize(payload)
        key = (alert.category, alert.pid, alert.message)
        now = datetime.now(timezone.utc)
        previous = self._last_seen.get(key)
        if previous is not None and (now - previous).total_seconds() < self.duplicate_window:
            return None
        self._last_seen[key] = now
        self._alerts.append(alert)
        return alert

    def add_many(self, payloads: Iterable[Alert | Dict[str, Any]]) -> list[Alert]:
        added = []
        for payload in payloads:
            alert = self.add(payload)
            if alert is not None:
                added.append(alert)
        return added

    def add_anomaly_alerts(self, alerts: Iterable[Dict[str, Any]]) -> list[Alert]:
        return self.add_many(alerts)

    def add_deadlock_cycle(self, result: Dict[str, Any]) -> list[Alert]:
        if result.get("has_cycle"):
            return self.add_many([{"category": "deadlock", "message": "Potential deadlock detected."}])
        return []

    def add_unsafe_state(self, result: Dict[str, Any]) -> list[Alert]:
        if result.get("safe") is False:
            return self.add_many([{"category": "unsafe_state", "message": "Unsafe resource-allocation state detected."}])
        return []

    def add_io_anomaly_alerts(
        self,
        anomaly_result: Dict[str, Any],
        pid: Optional[int] = None,
        process_name: Optional[str] = None,
    ) -> list[Alert]:
        """Convert io_anomaly results into alerts.

        Accepts the output of ``analyze_io_health()`` (or a single
        detector result).  For each sub-result with ``anomaly=True``,
        an ``Alert`` is created with the appropriate category, severity,
        and evidence embedded in the message.

        Parameters:
            anomaly_result – Dict from analyze_io_health() containing
                             ``io_spike``, ``io_stall``,
                             ``sustained_high_io``, ``rw_ratio_shift``
                             sub-dicts, each with an ``anomaly`` bool.
            pid            – Process ID to attach to each alert.
            process_name   – Process name for the message.

        Returns:
            List of Alert objects (may be empty if no anomalies).
        """
        if not isinstance(anomaly_result, dict):
            return []

        # Detector-key → alert category mapping.
        detector_map = {
            "io_spike": "io_spike",
            "io_stall": "io_stall",
            "sustained_high_io": "sustained_high_io",
            "rw_ratio_shift": "rw_ratio_shift",
        }

        alerts: list[Alert] = []
        for detector_key, category in detector_map.items():
            sub = anomaly_result.get(detector_key)
            if not isinstance(sub, dict) or not sub.get("anomaly"):
                continue

            severity_raw = str(sub.get("severity", "medium")).lower()
            severity = self._IO_SEVERITY_MAP.get(severity_raw, "WARNING")

            reason = sub.get("reason", self._messages.get(category, "I/O anomaly detected."))
            name_part = f"process={process_name} " if process_name else ""
            pid_part = f"pid={pid} " if pid is not None else ""
            identity = f"({name_part}{pid_part})".strip()
            if identity and identity != "()":
                identity = f" {identity}"
            else:
                identity = ""

            message = f"{reason}{identity}"

            evidence = self._build_io_evidence(sub)
            if evidence:
                message = f"{message} Evidence: {evidence}."

            alert = Alert(
                timestamp=self._timestamp(sub.get("timestamp")),
                severity=severity,
                category=category,
                message=message,
                suggested_action=self._actions.get(category, "Investigate the alert."),
                pid=self._pid(pid),
            )
            alerts.append(alert)

        added = self.add_many(alerts)
        return added

    def add_io_classification_change_alert(
        self,
        pid: Optional[int],
        process_name: Optional[str],
        old_classification: str,
        new_classification: str,
        reason: str = "",
    ) -> Optional[Alert]:
        """Create an alert when a process's I/O classification changes.

        Parameters:
            pid                – Process ID.
            process_name       – Process name.
            old_classification – Previous classification (e.g. ``IO_BOUND``).
            new_classification – New classification.
            reason             – Optional human-readable reason string.

        Returns:
            Alert if created, ``None`` if suppressed by deduplication.
        """
        if old_classification == new_classification:
            return None

        name_part = f"process={process_name} " if process_name else ""
        pid_part = f"pid={pid} " if pid is not None else ""
        identity = f"({name_part}{pid_part})".strip()
        if identity and identity != "()":
            identity = f" {identity}"
        else:
            identity = ""

        message = (
            f"I/O classification changed{identity}: "
            f"{old_classification} -> {new_classification}."
        )
        if reason:
            message = f"{message} {reason}"

        alert = Alert(
            timestamp=self._timestamp(None),
            severity="WARNING",
            category="io_classification_change",
            message=message,
            suggested_action=self._actions["io_classification_change"],
            pid=self._pid(pid),
        )
        return self.add(alert)

    @staticmethod
    def _build_io_evidence(sub: Dict[str, Any]) -> str:
        """Extract a short evidence string from an anomaly sub-result."""
        parts: list[str] = []

        if sub.get("type") and sub["type"] != "none":
            parts.append(f"type={sub['type']}")

        for key in (
            "current_rate", "baseline_rate", "ratio",
            "last_active_rate", "silent_observations",
            "consecutive_high_count", "average_high_rate",
            "current_ratio", "baseline_ratio", "ratio_of_ratios",
        ):
            val = sub.get(key)
            if val is not None:
                parts.append(f"{key}={val}")

        return ", ".join(parts)
