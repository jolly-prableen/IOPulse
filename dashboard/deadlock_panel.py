from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import List

from dashboard.alert_engine import AlertEngine
from process_concurrency.deadlock.bankers_algorithm import bankers_algorithm
from process_concurrency.deadlock.resource_allocation_graph import ResourceAllocationGraph, detect_cycle


def parse_matrix_input(raw_text: str) -> List[List[int]]:
    """Parse a matrix string such as '1,2;3,4' into a list of integer rows."""
    if not raw_text or not raw_text.strip():
        raise ValueError("Matrix input cannot be empty.")

    rows = []
    for row_text in raw_text.strip().split(";"):
        values = [int(value.strip()) for value in row_text.split(",") if value.strip()]
        if not values:
            continue
        rows.append(values)

    if not rows:
        raise ValueError("No numeric matrix values were provided.")
    return rows


class DeadlockPanel(ttk.Frame):
    """Deadlock analysis tab using the existing RAG and Banker's Algorithm modules."""

    def __init__(self, parent: tk.Misc, alert_engine: AlertEngine | None = None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.alert_engine = alert_engine
        self.graph = ResourceAllocationGraph()
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        rag_frame = ttk.LabelFrame(self, text="Resource Allocation Graph")
        rag_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 10))
        rag_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.rag_process_var = tk.StringVar()
        self.rag_resource_var = tk.StringVar()
        self.rag_edge_type_var = tk.StringVar(value="request")

        ttk.Label(rag_frame, text="Process ID").grid(row=0, column=0, sticky="w", padx=(10, 5), pady=(10, 5))
        ttk.Entry(rag_frame, textvariable=self.rag_process_var).grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 5))

        ttk.Label(rag_frame, text="Resource ID").grid(row=1, column=0, sticky="w", padx=(10, 5), pady=(0, 5))
        ttk.Entry(rag_frame, textvariable=self.rag_resource_var).grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 5))

        ttk.Label(rag_frame, text="Edge Type").grid(row=2, column=0, sticky="w", padx=(10, 5), pady=(0, 5))
        ttk.Combobox(rag_frame, textvariable=self.rag_edge_type_var, state="readonly", values=["request", "allocation"]).grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=(0, 5))

        ttk.Button(rag_frame, text="Add Process", command=self.add_process).grid(row=0, column=2, sticky="ew", padx=(0, 10), pady=(10, 5))
        ttk.Button(rag_frame, text="Add Resource", command=self.add_resource).grid(row=1, column=2, sticky="ew", padx=(0, 10), pady=(0, 5))
        ttk.Button(rag_frame, text="Add Edge", command=self.add_edge).grid(row=2, column=2, sticky="ew", padx=(0, 10), pady=(0, 5))

        ttk.Button(rag_frame, text="Detect Cycle", command=self.detect_rag_cycle).grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 10))

        self.rag_status_var = tk.StringVar(value="No cycle checked yet.")
        ttk.Label(rag_frame, textvariable=self.rag_status_var, wraplength=420, justify="left").grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 10))

        bankers_frame = ttk.LabelFrame(self, text="Banker's Algorithm")
        bankers_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        bankers_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(bankers_frame, text="Available (comma-separated)").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        self.available_var = tk.StringVar(value="3,3,2")
        ttk.Entry(bankers_frame, textvariable=self.available_var).grid(row=1, column=0, sticky="ew", padx=10)

        ttk.Label(bankers_frame, text="Allocation (rows separated by ;, values separated by commas)").grid(row=2, column=0, sticky="w", padx=10, pady=(10, 5))
        self.allocation_var = tk.StringVar(value="0,1,0;2,0,0;3,0,2;2,1,1")
        ttk.Entry(bankers_frame, textvariable=self.allocation_var).grid(row=3, column=0, sticky="ew", padx=10)

        ttk.Label(bankers_frame, text="Maximum (rows separated by ;, values separated by commas)").grid(row=4, column=0, sticky="w", padx=10, pady=(10, 5))
        self.maximum_var = tk.StringVar(value="7,5,3;3,2,2;9,0,2;2,2,2")
        ttk.Entry(bankers_frame, textvariable=self.maximum_var).grid(row=5, column=0, sticky="ew", padx=10)

        ttk.Button(bankers_frame, text="Check Safe State", command=self.check_safe_state).grid(row=6, column=0, sticky="ew", padx=10, pady=(10, 10))

        self.bankers_result_var = tk.StringVar(value="")
        ttk.Label(bankers_frame, textvariable=self.bankers_result_var, justify="left", wraplength=420).grid(row=7, column=0, sticky="w", padx=10, pady=(0, 10))

    def add_process(self) -> None:
        process_id = self.rag_process_var.get().strip()
        if not process_id:
            messagebox.showerror("Invalid Process", "Process ID cannot be empty.")
            return
        self.graph.add_process(process_id)
        self.rag_status_var.set(f"Added process {process_id}.")

    def add_resource(self) -> None:
        resource_id = self.rag_resource_var.get().strip()
        if not resource_id:
            messagebox.showerror("Invalid Resource", "Resource ID cannot be empty.")
            return
        self.graph.add_resource(resource_id)
        self.rag_status_var.set(f"Added resource {resource_id}.")

    def add_edge(self) -> None:
        process_id = self.rag_process_var.get().strip()
        resource_id = self.rag_resource_var.get().strip()
        if not process_id or not resource_id:
            messagebox.showerror("Invalid Edge", "Both a process and a resource are required.")
            return
        edge_type = self.rag_edge_type_var.get()
        try:
            if edge_type == "request":
                self.graph.add_request_edge(process_id, resource_id)
            else:
                self.graph.add_allocation_edge(resource_id, process_id)
            self.rag_status_var.set(f"Added {edge_type} edge: {process_id} -> {resource_id}.")
        except Exception as exc:
            messagebox.showerror("RAG Error", f"Unable to add edge: {exc}")

    def detect_rag_cycle(self) -> None:
        try:
            result = detect_cycle(self.graph)
            self.rag_status_var.set(result.get("message", "No Deadlock Cycle Detected"))
            if self.alert_engine is not None:
                self.alert_engine.add_deadlock_cycle(result)
        except Exception as exc:
            messagebox.showerror("RAG Error", f"Unable to detect cycle: {exc}")

    def check_safe_state(self) -> None:
        try:
            available = [int(value.strip()) for value in self.available_var.get().split(",") if value.strip()]
            allocation = parse_matrix_input(self.allocation_var.get())
            maximum = parse_matrix_input(self.maximum_var.get())

            if len(allocation) != len(maximum):
                raise ValueError("Allocation and Maximum must have the same number of rows.")
            for row in allocation:
                if len(row) != len(available):
                    raise ValueError("Allocation row lengths must match the number of available resource types.")
            for row in maximum:
                if len(row) != len(available):
                    raise ValueError("Maximum row lengths must match the number of available resource types.")

            result = bankers_algorithm(available, allocation, maximum)
            if self.alert_engine is not None:
                self.alert_engine.add_unsafe_state(result)
            safe_sequence = ", ".join(result.get("safe_sequence", [])) if result.get("safe_sequence") else "None"
            message = (
                f"Status: {result.get('message')}\n"
                f"Need Matrix: {result.get('need')}\n"
                f"Safe Sequence: {safe_sequence}"
            )
            self.bankers_result_var.set(message)
        except Exception as exc:
            messagebox.showerror("Banker's Algorithm Error", f"Invalid input: {exc}")
