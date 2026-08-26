from __future__ import annotations

import tkinter as tk
from datetime import datetime, timezone
from tkinter import ttk
from typing import Any, Dict, List

import psutil

from dashboard.alert_engine import AlertEngine
from process_concurrency.anomaly.process_anomaly import ProcessAnomalyDetector
from process_concurrency.process_monitor.process_monitor import get_processes


class AnomalyPanel(ttk.Frame):
    """Display process anomalies using the existing anomaly detector."""

    def __init__(self, parent: tk.Misc, alert_engine: AlertEngine | None = None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.alert_engine = alert_engine
        self.detector = ProcessAnomalyDetector()
        self.alerts: List[Dict[str, Any]] = []
        self._after_id: str | None = None
        self._build_ui()
        self.refresh_anomalies()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        title = ttk.Label(self, text="Process Anomaly Detection", font=("TkDefaultFont", 11, "bold"))
        title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        columns = ("timestamp", "severity", "category", "pid", "process_name", "message")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=17)
        for key, label in {
            "timestamp": "Timestamp",
            "severity": "Severity",
            "category": "Category",
            "pid": "PID",
            "process_name": "Process Name",
            "message": "Message",
        }.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, anchor="center", width=140)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def _safe_observations(self):
        observations = []
        for process in get_processes():
            try:
                try:
                    cpu_times = psutil.Process(int(process["pid"])).cpu_times()
                    cpu_time_data = {"user": cpu_times.user, "system": cpu_times.system}
                except (psutil.Error, KeyError, TypeError, ValueError):
                    cpu_time_data = None
                observations.append(
                    {
                        "pid": int(process.get("pid", -1)),
                        "name": str(process.get("name", "unknown")).strip() or "unknown",
                        "cpu_percent": float(process.get("cpu_percent", 0.0)),
                        "status": str(process.get("status", "unknown")).strip() or "unknown",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "cpu_times": cpu_time_data,
                    }
                )
            except Exception:
                continue
        return observations

    def refresh_anomalies(self) -> None:
        try:
            alerts = []
            for observation in self._safe_observations():
                alerts.extend(self.detector.record_observation(observation))
            if self.alert_engine is not None:
                self.alert_engine.add_anomaly_alerts(alerts)
            self.alerts = alerts[-50:]
            self.tree.delete(*self.tree.get_children())
            for alert in self.alerts:
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        alert.get("timestamp", ""),
                        alert.get("severity", ""),
                        alert.get("category", ""),
                        alert.get("pid", ""),
                        alert.get("process_name", ""),
                        alert.get("message", ""),
                    ),
                )
        except Exception:
            pass

        self._after_id = self.after(2000, self.refresh_anomalies)

    def stop(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
