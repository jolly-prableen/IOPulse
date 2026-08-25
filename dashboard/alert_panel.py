from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from dashboard.alert_engine import AlertEngine


class AlertPanel(ttk.Frame):
    """Display recent normalized alerts from the shared alert engine."""

    def __init__(self, parent: tk.Misc, engine: AlertEngine, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.engine = engine
        self._after_id: str | None = None
        self._build_ui()
        self.refresh_alerts()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ttk.Label(self, text="System Alerts", font=("TkDefaultFont", 11, "bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 5)
        )
        columns = ("timestamp", "severity", "category", "pid", "message", "suggested_action")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=17)
        headings = {
            "timestamp": "Timestamp",
            "severity": "Severity",
            "category": "Category",
            "pid": "PID",
            "message": "Message",
            "suggested_action": "Suggested Action",
        }
        for column, heading in headings.items():
            self.tree.heading(column, text=heading)
            self.tree.column(column, anchor="center", width=150, minwidth=100)
        self.tree.column("message", width=280)
        self.tree.column("suggested_action", width=280)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def refresh_alerts(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for alert in self.engine.alerts:
            self.tree.insert(
                "",
                "end",
                values=(
                    alert.timestamp,
                    alert.severity,
                    alert.category,
                    "" if alert.pid is None else alert.pid,
                    alert.message,
                    alert.suggested_action,
                ),
            )
        self._after_id = self.after(1000, self.refresh_alerts)

    def stop(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
