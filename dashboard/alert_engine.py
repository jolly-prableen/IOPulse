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
    }
    _messages = {
        "runaway_process": "Possible runaway process detected.",
        "zombie_process": "Zombie process detected.",
        "cpu_starvation": "Possible CPU starvation detected.",
        "deadlock": "Potential deadlock detected.",
        "unsafe_state": "Unsafe resource-allocation state detected.",
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
        data = payload.as_dict() if isinstance(payload, Alert) else dict(payload)
        category = str(data.get("category", "general"))
        if category == "possible_cpu_starvation":
            category = "cpu_starvation"

        severity = str(data.get("severity", "INFO")).upper()
        if category in {"deadlock", "unsafe_state"}:
            severity = "CRITICAL"
        elif category in self._actions:
            severity = "WARNING"
        if severity not in SEVERITIES:
            severity = "INFO"

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
