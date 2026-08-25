from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List

from process_concurrency.process_monitor.process_monitor import get_processes


class ProcessMonitorPanel(ttk.Frame):
    """Live process monitor view that refreshes using Tkinter after()."""

    def __init__(self, parent: tk.Misc, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self._after_id: str | None = None
        self._build_ui()
        self.refresh_processes()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.title = ttk.Label(self, text="Real-Time Process Monitor", font=("TkDefaultFont", 11, "bold"))
        self.title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        button_row = ttk.Frame(self)
        button_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        button_row.grid_columnconfigure(0, weight=1)

        self.status_label = ttk.Label(button_row, text="Auto-refreshing", anchor="w")
        self.status_label.grid(row=0, column=0, sticky="w")

        self.refresh_button = ttk.Button(button_row, text="Refresh Now", command=self.refresh_processes)
        self.refresh_button.grid(row=0, column=1, sticky="e", padx=(10, 0))

        columns = ("pid", "name", "cpu", "memory", "priority", "status")
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=18,
        )

        self.tree.heading("pid", text="PID")
        self.tree.heading("name", text="NAME")
        self.tree.heading("cpu", text="CPU%")
        self.tree.heading("memory", text="MEM%")
        self.tree.heading("priority", text="PRIORITY")
        self.tree.heading("status", text="STATUS")

        for column in columns:
            self.tree.column(column, anchor="center", width=110, minwidth=90)
        self.tree.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def _safe_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in get_processes():
            try:
                cpu = float(item.get("cpu_percent", 0.0))
                memory = float(item.get("memory_percent", 0.0))
                priority_value = item.get("priority")
                rows.append(
                    {
                        "pid": str(item.get("pid", "N/A")),
                        "name": str(item.get("name", "unknown")).strip() or "unknown",
                        "cpu": f"{cpu:.1f}",
                        "memory": f"{memory:.1f}",
                        "priority": "N/A" if priority_value is None else str(priority_value),
                        "status": str(item.get("status", "unknown")).strip() or "unknown",
                    }
                )
            except Exception:
                continue
        return rows

    def refresh_processes(self) -> None:
        try:
            self.tree.delete(*self.tree.get_children())
            rows = self._safe_rows()
            for row in rows:
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        row["pid"],
                        row["name"],
                        row["cpu"],
                        row["memory"],
                        row["priority"],
                        row["status"],
                    ),
                )
            if rows:
                self.status_label.config(text=f"Auto-refreshing ({len(rows)} processes visible)")
            else:
                self.status_label.config(text="Auto-refreshing (no accessible processes)")
        except Exception:
            self.status_label.config(text="Auto-refreshing (refresh error)")

        if self._after_id is not None:
            self.after_cancel(self._after_id)
        self._after_id = self.after(1000, self.refresh_processes)

    def stop(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
