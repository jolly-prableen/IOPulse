import tkinter as tk
from tkinter import ttk

from dashboard.alert_engine import AlertEngine
from dashboard.alert_panel import AlertPanel
from dashboard.anomaly_panel import AnomalyPanel
from dashboard.deadlock_panel import DeadlockPanel
from dashboard.process_panel import ProcessMonitorPanel
from dashboard.scheduling_panel import SchedulingPanel


def build_dashboard(root: tk.Tk) -> tuple[ttk.Notebook, AlertEngine]:
    root.title("OS Sentinel Dashboard")
    root.geometry("1100x700")
    root.minsize(800, 500)

    container = ttk.Frame(root, padding=8)
    container.pack(fill="both", expand=True)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(0, weight=1)

    notebook = ttk.Notebook(container)
    notebook.grid(row=0, column=0, sticky="nsew")

    alert_engine = AlertEngine()
    process_panel = ProcessMonitorPanel(notebook)
    scheduling_panel = SchedulingPanel(notebook)
    deadlock_panel = DeadlockPanel(notebook, alert_engine)
    anomaly_panel = AnomalyPanel(notebook, alert_engine)
    alert_panel = AlertPanel(notebook, alert_engine)

    notebook.add(process_panel, text="Process Monitor")
    notebook.add(scheduling_panel, text="CPU Scheduling")
    notebook.add(deadlock_panel, text="Deadlock")
    notebook.add(anomaly_panel, text="Anomaly Detection")
    notebook.add(alert_panel, text="Alerts")

    def close_dashboard() -> None:
        process_panel.stop()
        anomaly_panel.stop()
        alert_panel.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_dashboard)

    return notebook, alert_engine


def main() -> None:
    root = tk.Tk()
    build_dashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
