from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from process_concurrency.scheduling.integration import generate_gantt_chart, schedule_processes


def _normalize_process_input(processes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize GUI process rows into the data structure expected by the scheduling modules."""
    normalized: List[Dict[str, Any]] = []
    for process in processes:
        try:
            normalized.append(
                {
                    "pid": str(process["pid"]),
                    "arrival_time": float(process["arrival_time"]),
                    "burst_time": float(process["burst_time"]),
                    **({"priority": int(process["priority"])} if "priority" in process and process.get("priority") is not None else {}),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive UI guard
            raise ValueError(f"Invalid process entry: {process}") from exc
    return normalized


class SchedulingPanel(ttk.Frame):
    """Scheduling simulation panel that delegates algorithm execution to the existing modules."""

    def __init__(self, parent: tk.Misc, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.processes: List[Dict[str, Any]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        title = ttk.Label(self, text="CPU Scheduling Simulation", font=("TkDefaultFont", 11, "bold"))
        title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        fields = ttk.Frame(self)
        fields.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        fields.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.pid_var = tk.StringVar()
        self.arrival_var = tk.StringVar()
        self.burst_var = tk.StringVar()
        self.priority_var = tk.StringVar()
        self.quantum_var = tk.StringVar(value="2")

        ttk.Label(fields, text="Process ID").grid(row=0, column=0, sticky="w", padx=(0, 5))
        ttk.Entry(fields, textvariable=self.pid_var).grid(row=0, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(fields, text="Arrival Time").grid(row=0, column=2, sticky="w", padx=(0, 5))
        ttk.Entry(fields, textvariable=self.arrival_var).grid(row=0, column=3, sticky="ew", padx=(0, 10))

        ttk.Label(fields, text="Burst Time").grid(row=0, column=4, sticky="w", padx=(0, 5))
        ttk.Entry(fields, textvariable=self.burst_var).grid(row=0, column=5, sticky="ew")

        ttk.Label(fields, text="Priority").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(5, 0))
        ttk.Entry(fields, textvariable=self.priority_var).grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(5, 0))

        ttk.Label(fields, text="Time Quantum").grid(row=1, column=2, sticky="w", padx=(0, 5), pady=(5, 0))
        ttk.Entry(fields, textvariable=self.quantum_var).grid(row=1, column=3, sticky="ew", padx=(0, 10), pady=(5, 0))

        add_button = ttk.Button(fields, text="Add Process", command=self.add_process)
        add_button.grid(row=1, column=4, sticky="ew", pady=(5, 0), padx=(0, 5))

        self.algorithm_var = tk.StringVar(value="fcfs")
        ttk.Label(fields, text="Algorithm").grid(row=2, column=0, sticky="w", padx=(0, 5), pady=(10, 0))
        algorithm_combo = ttk.Combobox(fields, textvariable=self.algorithm_var, state="readonly", values=["fcfs", "sjf", "priority", "round_robin"])
        algorithm_combo.grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=(10, 0))

        run_button = ttk.Button(fields, text="Run Simulation", command=self.run_simulation)
        run_button.grid(row=2, column=2, columnspan=2, sticky="ew", pady=(10, 0), padx=(0, 10))

        clear_button = ttk.Button(fields, text="Clear", command=self.clear_processes)
        clear_button.grid(row=2, column=4, sticky="ew", pady=(10, 0))

        tree_container = ttk.Frame(self)
        tree_container.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_rowconfigure(0, weight=1)

        columns = ("pid", "arrival", "burst", "priority")
        self.process_tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=8)
        self.process_tree.heading("pid", text="Process ID")
        self.process_tree.heading("arrival", text="Arrival")
        self.process_tree.heading("burst", text="Burst")
        self.process_tree.heading("priority", text="Priority")
        for column in columns:
            self.process_tree.column(column, anchor="center", width=120)
        self.process_tree.grid(row=0, column=0, sticky="nsew")

        output_container = ttk.LabelFrame(self, text="Simulation Results")
        output_container.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        output_container.grid_columnconfigure(0, weight=1)
        output_container.grid_rowconfigure(0, weight=1)

        self.result_tree = ttk.Treeview(output_container, columns=("pid", "arrival", "burst", "start", "completion", "turnaround", "waiting"), show="headings", height=8)
        for text, key in {
            "Process ID": "pid",
            "Arrival": "arrival",
            "Burst": "burst",
            "Start": "start",
            "Completion": "completion",
            "Turnaround": "turnaround",
            "Waiting": "waiting",
        }.items():
            self.result_tree.heading(key, text=text)
            self.result_tree.column(key, anchor="center", width=110)
        self.result_tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.summary_var = tk.StringVar(value="")
        ttk.Label(output_container, textvariable=self.summary_var, justify="left").grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))

        self.chart_label = ttk.Label(output_container, text="Gantt chart will appear here", justify="left")
        self.chart_label.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 10))

    def add_process(self) -> None:
        try:
            process = {
                "pid": self.pid_var.get().strip(),
                "arrival_time": self.arrival_var.get().strip(),
                "burst_time": self.burst_var.get().strip(),
                "priority": self.priority_var.get().strip() if self.priority_var.get().strip() else "0",
            }
            if not process["pid"]:
                raise ValueError("Process ID is required.")
            float(process["arrival_time"])
            float(process["burst_time"])
            int(process["priority"])
        except Exception:
            messagebox.showerror("Invalid Process", "Please enter a valid process ID, arrival time, burst time, and priority.")
            return

        self.processes.append(process)
        self.process_tree.insert("", "end", values=(process["pid"], process["arrival_time"], process["burst_time"], process["priority"]))
        self.pid_var.set("")
        self.arrival_var.set("")
        self.burst_var.set("")
        self.priority_var.set("")

    def clear_processes(self) -> None:
        self.processes = []
        self.process_tree.delete(*self.process_tree.get_children())
        self.result_tree.delete(*self.result_tree.get_children())
        self.summary_var.set("")
        self.chart_label.config(text="Gantt chart will appear here")

    def run_simulation(self) -> None:
        if not self.processes:
            messagebox.showwarning("No Processes", "Add at least one process before running the simulation.")
            return

        algorithm = self.algorithm_var.get()
        try:
            normalized = _normalize_process_input(self.processes)
            if algorithm == "round_robin":
                quantum = float(self.quantum_var.get())
                if quantum <= 0:
                    raise ValueError("Time quantum must be greater than zero.")
                result = schedule_processes(algorithm, normalized, time_quantum=quantum)
            else:
                result = schedule_processes(algorithm, normalized)

            self.result_tree.delete(*self.result_tree.get_children())
            for item in result.get("schedule", []):
                self.result_tree.insert(
                    "",
                    "end",
                    values=(
                        item.get("pid", ""),
                        item.get("arrival_time", ""),
                        item.get("burst_time", ""),
                        item.get("start_time", ""),
                        item.get("completion_time", ""),
                        item.get("turnaround_time", ""),
                        item.get("waiting_time", ""),
                    ),
                )

            avg_wait = result.get("average_waiting_time", 0.0)
            avg_turn = result.get("average_turnaround_time", 0.0)
            self.summary_var.set(
                f"Average Waiting Time: {avg_wait:.2f}   |   Average Turnaround Time: {avg_turn:.2f}"
            )

            chart_path = os.path.join(os.getcwd(), "dashboard_gantt.png")
            try:
                generate_gantt_chart(result, save_path=chart_path, show_plot=False)
                self.chart_label.config(text=f"Gantt chart saved to: {chart_path}")
            except Exception:
                self.chart_label.config(text="Gantt chart not generated for this simulation.")
        except Exception as exc:
            messagebox.showerror("Scheduling Error", f"Unable to run the selected algorithm: {exc}")
