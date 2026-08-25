import unittest

import tkinter as tk

from dashboard.main import build_dashboard


class TestDashboard(unittest.TestCase):
    def test_builds_all_final_dashboard_tabs(self):
        root = tk.Tk()
        try:
            notebook, _ = build_dashboard(root)
            root.update_idletasks()
            labels = [notebook.tab(tab, "text") for tab in notebook.tabs()]
            panel_names = [notebook.nametowidget(tab).__class__.__name__ for tab in notebook.tabs()]

            self.assertEqual(
                labels,
                ["Process Monitor", "CPU Scheduling", "Deadlock", "Anomaly Detection", "Alerts"],
            )
            self.assertEqual(
                panel_names,
                ["ProcessMonitorPanel", "SchedulingPanel", "DeadlockPanel", "AnomalyPanel", "AlertPanel"],
            )
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
