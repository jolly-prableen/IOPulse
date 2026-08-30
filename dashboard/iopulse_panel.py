"""
dashboard/iopulse_panel.py – IOPulse Dashboard Tab
OS Sentinel → IOPulse

=== PURPOSE ===
A Tkinter + matplotlib tab that visualizes the output of the IOPulse
intelligence modules:

    Section A – Live I/O overview cards
    Section B – Process I/O table
    Section C – CPU vs I/O behaviour scatter plot
    Section D – Read/write/total throughput history graph
    Section E – Anomaly panel (spike / stall / sustained / ratio shift)
    Section F – Disk scheduling comparison (FCFS / SSTF / SCAN / C-SCAN)
    Section G – "Why?" explainability area
    Section H – Refresh/control bar

=== ARCHITECTURE ===
The panel contains ZERO anomaly-detection / algorithm logic.  It only:
  1. Collects telemetry via intelligence/io_metrics.ProcessIOCollector.
  2. Classifies via intelligence/io_classifier.ProcessIOClassifier.
  3. Detects anomalies via intelligence/io_anomaly.analyze_io_health().
  4. Runs disk scheduling via intelligence/io_disk_bridge.
  5. Feeds alerts into dashboard/alert_engine.AlertEngine.

All pure-data helpers at the top of this module are GUI-free and are
unit-tested in tests/test_iopulse_panel.py.
"""

from __future__ import annotations

import tkinter as tk
from collections import deque
from tkinter import ttk, messagebox
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("TkAgg")  # Must be set before importing pyplot
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from dashboard.alert_engine import AlertEngine
from intelligence.io_anomaly import analyze_io_health
from intelligence.io_classifier import ProcessIOClassifier
from intelligence.io_disk_bridge import analyze_process_io_scheduling
from intelligence.io_metrics import ProcessIOCollector

# ===================================================================
# Style constants (dark palette shared with the rest of the project)
# ===================================================================
COLORS = {
    "bg_dark":      "#1e1e2e",
    "bg_surface":   "#282a3a",
    "bg_card":      "#313244",
    "text_primary": "#cdd6f4",
    "text_muted":   "#a6adc8",
    "accent_blue":  "#89b4fa",
    "accent_green": "#a6e3a1",
    "accent_peach": "#fab387",
    "warning":      "#f9e2af",
    "error":        "#f38ba8",
    "header_bg":    "#45475a",
}

FONT_FAMILY = "Segoe UI"
FONT_BODY   = (FONT_FAMILY, 10)
FONT_MONO   = ("Consolas", 10)
FONT_SMALL  = (FONT_FAMILY, 9)

# Marker / colour scheme for the CPU-vs-I/O scatter (Section C)
CLASSIFICATION_STYLE = {
    "CPU_BOUND": {"color": COLORS["accent_blue"],  "marker": "^", "label": "CPU Bound"},
    "IO_BOUND":  {"color": COLORS["accent_green"], "marker": "o", "label": "I/O Bound"},
    "BALANCED":  {"color": COLORS["accent_peach"], "marker": "s", "label": "Balanced"},
    "IDLE":      {"color": COLORS["text_muted"],   "marker": "x", "label": "Idle"},
}

# Keep the most recent throughput series points per process.
THROUGHPUT_HISTORY_MAX = 60


# ===================================================================
# GUI-free data preparation helpers (unit-tested)
# ===================================================================

def format_bytes_per_sec(bps: Any) -> str:
    """Format a bytes-per-second value into a human-readable string."""
    try:
        val = float(bps)
    except (TypeError, ValueError):
        return "0 B/s"
    if val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f} GB/s"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.2f} MB/s"
    if val >= 1_000:
        return f"{val / 1_000:.2f} KB/s"
    return f"{val:.0f} B/s"


def format_classification(classification: Any) -> str:
    """Map a classification code to friendly display text."""
    mapping = {
        "CPU_BOUND": "CPU Bound",
        "IO_BOUND": "I/O Bound",
        "BALANCED": "Balanced",
        "IDLE": "Idle",
        "": "—",
        "None": "—",
    }
    key = str(classification)
    return mapping.get(key, key.title().replace("_", " ") if key else "—")


def format_severity(severity: Any) -> str:
    """Map an anomaly severity code to display text."""
    mapping = {
        "none": "Normal",
        "low": "Low",
        "medium": "Medium",
        "high": "High",
        "critical": "Critical",
        "INFO": "Info",
        "WARNING": "Warning",
        "CRITICAL": "Critical",
    }
    return mapping.get(str(severity), str(severity))


def validate_refresh_interval(text: Any) -> Tuple[bool, str]:
    """Validate a refresh-interval string.

    Returns ``(ok, message)`` where ``ok`` is True for a valid interval
    in the range [500, 30000] ms.
    """
    if text is None or str(text).strip() == "":
        return False, "Interval cannot be empty."
    try:
        value = int(str(text).strip())
    except (TypeError, ValueError):
        return False, "Interval must be a whole number of milliseconds."
    if value < 500:
        return False, "Interval must be at least 500 ms."
    if value > 30000:
        return False, "Interval must be at most 30000 ms."
    return True, ""


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def prepare_overview_data(
    metrics_list: List[Dict[str, Any]],
    classifications: List[Dict[str, Any]],
    health_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the Section A overview-card data.

    Parameters:
        metrics_list     – Output of ProcessIOCollector.collect_all().
        classifications  – Output of ProcessIOClassifier.classify_batch().
        health_results   – One analyze_io_health() dict per monitored process.

    Returns:
        A dict with aggregated totals and counts.  All non-float output
        values are rounded where appropriate.
    """
    total_read = 0.0
    total_write = 0.0
    total_io = 0.0
    for m in metrics_list:
        if not isinstance(m, dict):
            continue
        total_read += _safe_float(m.get("read_bytes_per_sec"))
        total_write += _safe_float(m.get("write_bytes_per_sec"))
        total_io += _safe_float(m.get("total_io_bytes_per_sec"))

    class_counts = {"CPU_BOUND": 0, "IO_BOUND": 0, "BALANCED": 0, "IDLE": 0}
    for c in classifications:
        key = str(c.get("classification", "IDLE"))
        if key not in class_counts:
            key = "IDLE"
        class_counts[key] += 1

    active_anomalies = sum(
        1 for result in health_results
        if isinstance(result, dict) and result.get("any_anomaly", False)
    )

    return {
        "total_processes": len(metrics_list),
        "total_read_throughput": round(total_read, 2),
        "total_write_throughput": round(total_write, 2),
        "total_io_throughput": round(total_io, 2),
        "cpu_bound_count": class_counts["CPU_BOUND"],
        "io_bound_count": class_counts["IO_BOUND"],
        "balanced_count": class_counts["BALANCED"],
        "idle_count": class_counts["IDLE"],
        "active_anomalies": active_anomalies,
    }


def extract_anomaly_evidence(sub: Dict[str, Any]) -> str:
    """Extract a summary of the numeric evidence from an anomaly result."""
    parts: List[str] = []
    for key in (
        "current_rate", "baseline_rate", "ratio",
        "last_active_rate", "silent_observations",
        "consecutive_high_count", "average_high_rate",
        "current_ratio", "baseline_ratio", "ratio_of_ratios",
    ):
        value = sub.get(key)
        if value is not None:
            parts.append(f"{key}={value}")
    return ", ".join(parts)


def prepare_process_table_data(
    metrics_list: List[Dict[str, Any]],
    classifications: List[Dict[str, Any]],
    health_map: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build Section B process-table rows.

    ``health_map`` maps pid -> analyze_io_health() result dict.

    Returns a list of display-ready row dicts (values formatted for the
    treeview, plus raw values for the explainability area).
    """
    class_map: Dict[int, Dict[str, Any]] = {}
    for c in classifications:
        pid = c.get("pid")
        if pid is not None:
            class_map[int(pid)] = c

    rows: List[Dict[str, Any]] = []
    for m in metrics_list:
        if not isinstance(m, dict):
            continue
        try:
            pid = int(m.get("pid"))
        except (TypeError, ValueError):
            continue

        cls_data = class_map.get(pid, {})
        health = health_map.get(pid, {})
        anomaly_flags: List[str] = []
        for key in ("io_spike", "io_stall", "sustained_high_io", "rw_ratio_shift"):
            sub = health.get(key)
            if isinstance(sub, dict) and sub.get("anomaly"):
                anomaly_flags.append(str(sub.get("type", key)))

        status = ", ".join(anomaly_flags) if anomaly_flags else "Normal"

        cpu = _safe_float(m.get("cpu_percent"))
        read = _safe_float(m.get("read_bytes_per_sec"))
        write = _safe_float(m.get("write_bytes_per_sec"))
        total = _safe_float(m.get("total_io_bytes_per_sec"))
        confidence = _safe_float(cls_data.get("confidence"))

        rows.append(
            {
                "pid": str(pid),
                "pid_raw": pid,
                "name": str(m.get("name", "unknown") or "unknown")[:24],
                "name_raw": str(m.get("name", "unknown") or "unknown"),
                "cpu": f"{cpu:.1f}",
                "cpu_raw": cpu,
                "read_rate": format_bytes_per_sec(read),
                "read_rate_raw": read,
                "write_rate": format_bytes_per_sec(write),
                "write_rate_raw": write,
                "total_io_rate": format_bytes_per_sec(total),
                "total_io_rate_raw": total,
                "classification": format_classification(cls_data.get("classification")),
                "classification_raw": str(cls_data.get("classification", "IDLE")),
                "confidence": f"{confidence:.2f}",
                "confidence_raw": confidence,
                "status": status,
                "status_raw": status,
                "reason": str(cls_data.get("reason", "")),
            }
        )
    return rows


def prepare_classification_scatter_data(
    classifications: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build Section C scatter-plot series.

    Returns a dict mapping each classification to lists of (x=CPU%,
    y=I/O B/s, name) points, plus a total point count.
    """
    series: Dict[str, Dict[str, Any]] = {}
    total_points = 0
    for c in classifications:
        if not isinstance(c, dict):
            continue
        key = str(c.get("classification", "IDLE"))
        if key not in CLASSIFICATION_STYLE:
            key = "IDLE"
        if key not in series:
            series[key] = {"x": [], "y": [], "names": []}
        series[key]["x"].append(_safe_float(c.get("cpu_percent")))
        series[key]["y"].append(_safe_float(c.get("total_io_bytes_per_sec")))
        series[key]["names"].append(str(c.get("process_name", "unknown")))
        total_points += 1
    return {"series": series, "total_points": total_points}


def prepare_throughput_history(
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build Section D per-process throughput history.

    ``history`` is a list of metric dicts (each containing
    ``read_bytes_per_sec``, ``write_bytes_per_sec``,
    ``total_io_bytes_per_sec`` and ``timestamp``), oldest first.

    Returns:
        {
            "timestamps": [float, ...],
            "read":  [float, ...],
            "write": [float, ...],
            "total": [float, ...],
        }
    """
    timestamps: List[float] = []
    read: List[float] = []
    write: List[float] = []
    total: List[float] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        timestamps.append(_safe_float(entry.get("timestamp")))
        read.append(_safe_float(entry.get("read_bytes_per_sec")))
        write.append(_safe_float(entry.get("write_bytes_per_sec")))
        total.append(_safe_float(entry.get("total_io_bytes_per_sec")))
    return {"timestamps": timestamps, "read": read, "write": write, "total": total}


def prepare_anomaly_display_data(
    pids: List[Any],
    health_results: List[Dict[str, Any]],
    class_map: Optional[Dict[int, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Build Section E anomaly-table rows.

    Parameters:
        pids           – Monitored pids (parallel to ``health_results``).
        health_results – One analyze_io_health() dict per pid.
        class_map      – Optional pid -> classification dict (for names).

    Returns:
        Display-ready rows, one per triggered detector.
    """
    class_map = class_map or {}
    rows: List[Dict[str, Any]] = []
    for pid, health in zip(pids, health_results):
        if not isinstance(health, dict):
            continue
        if not health.get("any_anomaly", False):
            continue
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            pid_int = pid

        cls_data = class_map.get(pid_int, {})
        name = str(cls_data.get("process_name", "unknown") or "unknown")

        for key in ("io_spike", "io_stall", "sustained_high_io", "rw_ratio_shift"):
            sub = health.get(key)
            if not isinstance(sub, dict) or not sub.get("anomaly"):
                continue
            rows.append(
                {
                    "pid": str(pid_int),
                    "process_name": name[:24],
                    "severity": format_severity(sub.get("severity")),
                    "type": str(sub.get("type", key)),
                    "reason": str(sub.get("reason", "")),
                    "evidence": extract_anomaly_evidence(sub),
                }
            )
    return rows


def prepare_scheduling_display_data(
    scheduling_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build Section F scheduling-comparison display data.

    Returns a dict suitable for rendering the four-algorithm comparison
    table and the recommendation line.
    """
    if not isinstance(scheduling_result, dict):
        return {
            "simulation_note": "",
            "request_count": 0,
            "algorithms": {},
            "recommended": "—",
            "recommendation_reason": "No telemetry available yet.",
        }

    analysis = scheduling_result.get("scheduling_analysis", {})
    movements = analysis.get("total_head_movements", {}) or {}
    algorithms: Dict[str, Dict[str, Any]] = {}
    for name in ("FCFS", "SSTF", "SCAN", "C-SCAN"):
        algorithms[name] = {
            "head_movement": int(movements.get(name, 0) or 0),
            "request_count": int(
                (analysis.get("results", {}) or {}).get(name, {})
                .get("request_count", 0) or 0
            ),
        }

    return {
        "simulation_note": str(scheduling_result.get("simulation_note", "")),
        "request_count": int(analysis.get("request_count", 0) or 0),
        "algorithms": algorithms,
        "recommended": str(analysis.get("recommended_algorithm", "—") or "—"),
        "recommendation_reason": str(analysis.get("reason", "")),
    }


def prepare_explanation(kind: str, data: Optional[Dict[str, Any]]) -> str:
    """Build a human-readable "Why?" explanation (Section G).

    ``kind`` is one of: "classification", "anomaly", "scheduling".
    ``data`` is the relevant result dict from the corresponding
    intelligence module — the explanation is derived from real values.
    """
    if not isinstance(data, dict):
        return "No data selected. Select a process or alert to see reasoning."

    if kind == "classification":
        classification = str(data.get("classification", "IDLE"))
        cpu_score = _safe_float(data.get("cpu_score"))
        io_score = _safe_float(data.get("io_score"))
        cpu_pct = _safe_float(data.get("cpu_percent"))
        io_rate = _safe_float(data.get("total_io_bytes_per_sec"))
        reason = str(data.get("reason", ""))
        base = reason or (
            f"Process is classified as {classification} because CPU "
            f"({cpu_pct:.1f}%) and I/O ({format_bytes_per_sec(io_rate)}) "
            f"activity map to scores CPU={cpu_score:.2f}, I/O={io_score:.2f}."
        )
        confidence = _safe_float(data.get("confidence"))
        if confidence:
            base = f"{base} (confidence {confidence:.2f})"
        return base

    if kind == "anomaly":
        anomaly_type = str(data.get("type", "unknown"))
        severity = str(data.get("severity", "none"))
        reason = str(data.get("reason", ""))
        evidence = extract_anomaly_evidence(data)
        if reason:
            message = reason
        elif anomaly_type == "io_spike":
            message = (
                "I/O SPIKE detected because current throughput is "
                f"{data.get('ratio', 0.0)}x the recent baseline."
            )
        elif anomaly_type == "io_stall":
            message = (
                "I/O STALL detected because an active process has shown "
                "near-zero I/O for several consecutive observations."
            )
        elif anomaly_type == "sustained_high_io":
            message = (
                "SUSTAINED HIGH I/O detected because the process has kept "
                "its I/O rate above the threshold for consecutive "
                "observations."
            )
        elif anomaly_type == "rw_ratio_shift":
            message = (
                "RW RATIO SHIFT detected because the read/write balance has "
                "changed dramatically vs recent history."
            )
        else:
            message = f"Anomaly of type {anomaly_type} detected."
        if evidence:
            message = f"{message} Evidence: {evidence}."
        return f"{message} Severity: {format_severity(severity)}."

    if kind == "scheduling":
        recommended = str(data.get("recommended", "—") or "—")
        reason = str(data.get("recommendation_reason", ""))
        if reason:
            return reason
        if recommended == "—":
            return "No scheduling analysis performed yet."
        return f"Recommended algorithm: {recommended} (lowest total head movement)."

    return "No explanation available."


# ===================================================================
# IOPulse GUI panel
# ===================================================================

class IOPulsePanel(ttk.Frame):
    """IOPulse dashboard tab — Sections A through H."""

    DEFAULT_INTERVAL_MS = 2000
    MIN_INTERVAL_MS = 500
    MAX_INTERVAL_MS = 30000

    def __init__(
        self,
        parent: tk.Misc,
        alert_engine: Optional[AlertEngine] = None,
        *args,
        **kwargs,
    ):
        super().__init__(parent, *args, **kwargs)
        self.alert_engine = alert_engine
        self.collector = ProcessIOCollector()
        self.classifier = ProcessIOClassifier()

        self._after_id: Optional[str] = None
        self._running = True
        self._interval_ms = self.DEFAULT_INTERVAL_MS

        # Per-process throughput history for the Section D graph.
        self._history: Dict[int, deque] = {}

        # Last-prepared data (used by the explainability area).
        self._last_overview: Dict[str, Any] = {}
        self._last_rows: List[Dict[str, Any]] = []
        self._last_anomalies: List[Dict[str, Any]] = []
        self._last_scheduling: Dict[str, Any] = {}

        self._configure_styles()
        self._build_ui()
        self._schedule_refresh()

    # ---------------------------------------------------------------
    # Styling
    # ---------------------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        for name, config in {
            "IOPulse.Dark.TFrame": {"background": COLORS["bg_dark"]},
            "IOPulse.Card.TFrame": {"background": COLORS["bg_card"]},
            "IOPulse.Surface.TFrame": {"background": COLORS["bg_surface"]},
        }.items():
            style.configure(name, **config)

        for name, config in {
            "IOPulse.Header.TLabel": {
                "background": COLORS["bg_dark"],
                "foreground": COLORS["accent_blue"],
                "font": (FONT_FAMILY, 11, "bold"),
            },
            "IOPulse.Section.TLabel": {
                "background": COLORS["bg_dark"],
                "foreground": COLORS["text_primary"],
                "font": (FONT_FAMILY, 10, "bold"),
            },
            "IOPulse.Card.TLabel": {
                "background": COLORS["bg_card"],
                "foreground": COLORS["text_primary"],
                "font": FONT_BODY,
            },
            "IOPulse.Stat.TLabel": {
                "background": COLORS["bg_card"],
                "foreground": COLORS["text_muted"],
                "font": FONT_SMALL,
            },
            "IOPulse.BigNum.TLabel": {
                "background": COLORS["bg_card"],
                "foreground": COLORS["accent_blue"],
                "font": (FONT_FAMILY, 15, "bold"),
            },
            "IOPulse.Muted.TLabel": {
                "background": COLORS["bg_dark"],
                "foreground": COLORS["text_muted"],
                "font": FONT_SMALL,
            },
            "IOPulse.Good.TLabel": {
                "background": COLORS["bg_card"],
                "foreground": COLORS["accent_green"],
                "font": FONT_BODY,
            },
            "IOPulse.Warn.TLabel": {
                "background": COLORS["bg_card"],
                "foreground": COLORS["warning"],
                "font": FONT_BODY,
            },
        }.items():
            style.configure(name, **config)

        style.configure(
            "IOPulse.Treeview",
            background=COLORS["bg_surface"],
            foreground=COLORS["text_primary"],
            fieldbackground=COLORS["bg_surface"],
            font=FONT_MONO,
            rowheight=22,
        )
        style.configure(
            "IOPulse.Treeview.Heading",
            background=COLORS["header_bg"],
            foreground=COLORS["text_primary"],
            font=(FONT_FAMILY, 9, "bold"),
        )
        style.map(
            "IOPulse.Treeview",
            background=[("selected", COLORS["accent_blue"])],
            foreground=[("selected", COLORS["bg_dark"])],
        )

        style.configure(
            "IOPulse.TButton",
            background=COLORS["header_bg"],
            foreground=COLORS["text_primary"],
            font=FONT_BODY,
            padding=[10, 3],
        )
        style.map(
            "IOPulse.TButton",
            background=[("active", COLORS["accent_blue"])],
            foreground=[("active", COLORS["bg_dark"])],
        )

        style.configure(
            "IOPulse.TEntry",
            fieldbackground=COLORS["bg_surface"],
            foreground=COLORS["text_primary"],
            insertcolor=COLORS["text_primary"],
        )
        style.configure(
            "IOPulse.TSeparator",
            background=COLORS["header_bg"],
        )

    # ---------------------------------------------------------------
    # UI construction
    # ---------------------------------------------------------------

    def _build_ui(self) -> None:
        self.configure(style="IOPulse.Dark.TFrame")

        # --- Header + Control bar (Section H) -----------------------
        header_row = ttk.Frame(self, style="IOPulse.Dark.TFrame")
        header_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        header_row.columnconfigure(1, weight=1)

        ttk.Label(
            header_row,
            text="IOPulse — Process-Aware I/O Intelligence",
            style="IOPulse.Header.TLabel",
        ).grid(row=0, column=0, sticky="w")

        controls = ttk.Frame(header_row, style="IOPulse.Dark.TFrame")
        controls.grid(row=0, column=1, sticky="e")

        ttk.Label(controls, text="Refresh (ms):", style="IOPulse.Muted.TLabel").pack(
            side="left", padx=(0, 4)
        )
        self.entry_interval = ttk.Entry(controls, width=7, style="IOPulse.TEntry")
        self.entry_interval.insert(0, str(self.DEFAULT_INTERVAL_MS))
        self.entry_interval.pack(side="left", padx=(0, 6))

        self.btn_toggle = ttk.Button(
            controls, text="Pause", style="IOPulse.TButton", command=self.toggle_running
        )
        self.btn_toggle.pack(side="left", padx=(0, 4))
        ttk.Button(
            controls,
            text="Refresh Now",
            style="IOPulse.TButton",
            command=self.refresh_now,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            controls,
            text="Apply Interval",
            style="IOPulse.TButton",
            command=self.apply_interval,
        ).pack(side="left")

        self.lbl_status = ttk.Label(
            self, text="Waiting for telemetry…", style="IOPulse.Muted.TLabel"
        )
        self.lbl_status.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))

        # --- Content area: two-column layout ------------------------
        content = ttk.Frame(self, style="IOPulse.Dark.TFrame")
        content.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        self._build_left_column(content)
        self._build_right_column(content)

        # --- Status/explainability footer ---------------------------
        ttk.Separator(self, style="IOPulse.TSeparator").grid(
            row=3, column=0, sticky="ew", padx=8
        )
        self.explanation = tk.Text(
            self,
            height=4,
            bg=COLORS["bg_surface"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"],
            font=FONT_BODY,
            relief="flat",
            wrap="word",
            state="disabled",
        )
        self.explanation.grid(row=4, column=0, sticky="nsew", padx=8, pady=(4, 6))

        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

    # ---------------------------------------------------------------
    # Left column: Sections A, B, C, D
    # ---------------------------------------------------------------

    def _build_left_column(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent, style="IOPulse.Dark.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)

        # --- Section A: Overview cards -------------------------------
        ttk.Label(left, text="A. Live I/O Overview", style="IOPulse.Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        card_frame = ttk.Frame(left, style="IOPulse.Dark.TFrame")
        card_frame.grid(row=1, column=0, sticky="ew")
        self._build_overview_cards(card_frame)

        # --- Section B: Process I/O table ----------------------------
        ttk.Label(left, text="B. Process I/O Table", style="IOPulse.Section.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 4)
        )
        columns = (
            "pid", "name", "cpu", "read", "write", "total", "class", "conf", "status",
        )
        header_texts = {
            "pid": "PID",
            "name": "Process",
            "cpu": "CPU%",
            "read": "Read",
            "write": "Write",
            "total": "Total",
            "class": "Classification",
            "conf": "Conf.",
            "status": "Anomaly",
        }
        widths = {
            "pid": 55, "name": 140, "cpu": 55, "read": 85, "write": 85,
            "total": 90, "class": 95, "conf": 55, "status": 150,
        }
        self.tree_processes = ttk.Treeview(
            left, columns=columns, show="headings", style="IOPulse.Treeview", height=8
        )
        for col in columns:
            self.tree_processes.heading(col, text=header_texts[col])
            self.tree_processes.column(col, anchor="center", width=widths[col])
        self.tree_processes.column("name", anchor="w")
        self.tree_processes.column("status", anchor="w")
        self.tree_processes.grid(row=3, column=0, sticky="nsew")
        self.tree_processes.bind("<<TreeviewSelect>>", self._on_process_selected)

        # Row for the two graphs side by side --------------------------
        graph_row = ttk.Frame(left, style="IOPulse.Dark.TFrame")
        graph_row.grid(row=4, column=0, sticky="nsew", pady=(6, 0))
        graph_row.columnconfigure(0, weight=1)
        graph_row.columnconfigure(1, weight=1)
        graph_row.rowconfigure(0, weight=1)

        # --- Section C: CPU vs I/O scatter ----------------------------
        self._build_scatter(graph_row)
        # --- Section D: Throughput graph ------------------------------
        self._build_throughput_graph(graph_row)

    def _build_overview_cards(self, parent: ttk.Frame) -> None:
        specs = [
            ("Monitored Processes", "total_processes"),
            ("Read", "total_read_throughput"),
            ("Write", "total_write_throughput"),
            ("Total I/O", "total_io_throughput"),
            ("I/O Bound", "io_bound_count"),
            ("CPU Bound", "cpu_bound_count"),
            ("Balanced", "balanced_count"),
            ("Anomalies", "active_anomalies"),
        ]
        parent.columnconfigure(tuple(range(len(specs))), weight=1, uniform="card")
        self._card_labels = {}
        for index, (label, key) in enumerate(specs):
            card = ttk.Frame(parent, style="IOPulse.Card.TFrame")
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 4))
            ttk.Label(card, text=label, style="IOPulse.Stat.TLabel").pack(
                anchor="w", padx=6, pady=(6, 0)
            )
            num = ttk.Label(card, text="—", style="IOPulse.BigNum.TLabel")
            num.pack(anchor="w", padx=6, pady=(0, 6))
            self._card_labels[key] = num

    def _make_figure(self) -> Figure:
        figure = Figure(figsize=(4, 2.6), dpi=100, facecolor=COLORS["bg_card"])
        axis = figure.add_subplot(111)
        axis.set_facecolor(COLORS["bg_card"])
        axis.tick_params(colors=COLORS["text_muted"], labelsize=7)
        for spine in axis.spines.values():
            spine.set_color(COLORS["header_bg"])
        axis.grid(True, alpha=0.15, color=COLORS["text_muted"])
        return figure

    def _build_scatter(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, style="IOPulse.Dark.TFrame")
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        ttk.Label(frame, text="C. CPU vs I/O Behaviour", style="IOPulse.Section.TLabel").pack(
            anchor="w", pady=(0, 2)
        )
        self.scatter_figure = self._make_figure()
        self.scatter_canvas = FigureCanvasTkAgg(self.scatter_figure, master=frame)
        self.scatter_canvas.get_tk_widget().pack(fill="both", expand=True)
        self.lbl_scatter_empty = ttk.Label(
            frame,
            text="Waiting for telemetry to build the behaviour plot…",
            style="IOPulse.Muted.TLabel",
        )
        self.lbl_scatter_empty.pack(anchor="w")

    def _build_throughput_graph(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, style="IOPulse.Dark.TFrame")
        frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        ttk.Label(frame, text="D. Recent I/O Throughput", style="IOPulse.Section.TLabel").pack(
            anchor="w", pady=(0, 2)
        )
        self.thr_figure = self._make_figure()
        self.thr_canvas = FigureCanvasTkAgg(self.thr_figure, master=frame)
        self.thr_canvas.get_tk_widget().pack(fill="both", expand=True)
        self.lbl_thr_empty = ttk.Label(
            frame,
            text="Waiting for telemetry to build the throughput graph…",
            style="IOPulse.Muted.TLabel",
        )
        self.lbl_thr_empty.pack(anchor="w")

    # ---------------------------------------------------------------
    # Right column: Sections E, F
    # ---------------------------------------------------------------

    def _build_right_column(self, parent: ttk.Frame) -> None:
        right = ttk.Frame(parent, style="IOPulse.Dark.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        # --- Section E: Anomaly panel --------------------------------
        ttk.Label(right, text="E. I/O Anomalies", style="IOPulse.Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        anomaly_columns = ("pid", "process", "severity", "type")
        self.tree_anomalies = ttk.Treeview(
            right, columns=anomaly_columns, show="headings",
            style="IOPulse.Treeview", height=6,
        )
        headers = {"pid": "PID", "process": "Process", "severity": "Severity", "type": "Type"}
        widths = {"pid": 55, "process": 130, "severity": 80, "type": 130}
        for col in anomaly_columns:
            self.tree_anomalies.heading(col, text=headers[col])
            self.tree_anomalies.column(col, anchor="center", width=widths[col])
        self.tree_anomalies.column("process", anchor="w")
        self.tree_anomalies.grid(row=1, column=0, sticky="nsew")
        self.tree_anomalies.bind("<<TreeviewSelect>>", self._on_anomaly_selected)

        self.lbl_anomaly_empty = ttk.Label(
            right,
            text="No active I/O anomalies.",
            style="IOPulse.Muted.TLabel",
        )
        self.lbl_anomaly_empty.grid(row=1, column=0, sticky="w", padx=4, pady=(0, 2))

        # --- Section F: Disk scheduling comparison --------------------
        ttk.Label(right, text="F. Disk Scheduling Analysis", style="IOPulse.Section.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 4)
        )
        self.btn_run_scheduling = ttk.Button(
            right,
            text="Analyse Simulated Workload",
            style="IOPulse.TButton",
            command=self._run_scheduling,
        )
        self.btn_run_scheduling.grid(row=3, column=0, sticky="w", pady=(0, 4))

        self.lbl_simulation_note = ttk.Label(
            right,
            text="Simulated disk request workload derived from observed process I/O activity.",
            style="IOPulse.Muted.TLabel",
            wraplength=340,
        )
        self.lbl_simulation_note.grid(row=4, column=0, sticky="w", pady=(0, 4))

        sched_columns = ("algorithm", "requests", "movement")
        self.tree_scheduling = ttk.Treeview(
            right, columns=sched_columns, show="headings",
            style="IOPulse.Treeview", height=5,
        )
        for col, text, width in (
            ("algorithm", "Algorithm", 110),
            ("requests", "Requests", 80),
            ("movement", "Head Movement", 120),
        ):
            self.tree_scheduling.heading(col, text=text)
            self.tree_scheduling.column(col, anchor="center", width=width)
        self.tree_scheduling.grid(row=5, column=0, sticky="nsew", pady=(0, 4))

        self.lbl_recommendation = ttk.Label(
            right, text="Recommended: —", style="IOPulse.Card.TLabel", wraplength=340
        )
        self.lbl_recommendation.grid(row=6, column=0, sticky="w")

        self.lbl_recommendation_reason = ttk.Label(
            right, text="", style="IOPulse.Muted.TLabel", wraplength=340
        )
        self.lbl_recommendation_reason.grid(row=7, column=0, sticky="w")

    # ---------------------------------------------------------------
    # Data collection & preparation (all logic stays in modules)
    # ---------------------------------------------------------------

    def _collect_latest(self) -> None:
        """Gather telemetry and store structured results on this panel."""
        # 1. Collect raw process I/O metrics (uses io_metrics module).
        metrics_list = self.collector.collect_all() or []
        self._metrics_list = metrics_list

        # 2. Classify each process (uses io_classifier module).
        classifications = self.classifier.classify_batch(metrics_list)
        self._classifications = classifications

        # 3. Per-process anomaly health (uses io_anomaly module).
        pids = []
        health_results = []
        health_map: Dict[int, Dict[str, Any]] = {}
        for pid, metric in zip([m.get("pid") for m in metrics_list], metrics_list):
            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                continue
            history = list(self.collector.get_process_history(pid_int) or [])
            health = analyze_io_health(history) if history else {}
            pids.append(pid_int)
            health_results.append(health)
            health_map[pid_int] = health

            # Track per-process throughput history for the Section D graph.
            rate = metric.get("total_io_bytes_per_sec")
            if rate is not None:
                bucket = self._history.setdefault(pid_int, deque(maxlen=THROUGHPUT_HISTORY_MAX))
                bucket.append(metric)

        # 4. Feed detected anomalies into the shared alert engine.
        if self.alert_engine is not None:
            for metric in metrics_list:
                try:
                    pid_int = int(metric.get("pid"))
                except (TypeError, ValueError):
                    continue
                if pid_int not in health_map:
                    continue
                self.alert_engine.add_io_anomaly_alerts(
                    health_map[pid_int], pid_int, str(metric.get("name", "unknown"))
                )

        self._pids = pids
        self._health_results = health_results
        self._health_map = health_map

    def _render(self) -> None:
        """Refresh every widget from the last collected data."""
        metrics_list = getattr(self, "_metrics_list", [])
        classifications = getattr(self, "_classifications", [])
        health_map = getattr(self, "_health_map", {})
        pids = getattr(self, "_pids", [])
        health_results = getattr(self, "_health_results", [])
        scheduling = getattr(self, "_scheduling", None)

        # --- Section A cards ---
        overview = prepare_overview_data(metrics_list, classifications, health_results)
        self._last_overview = overview
        for key, label in (
            ("total_processes", self._card_labels["total_processes"]),
            ("total_read_throughput", self._card_labels["total_read_throughput"]),
            ("total_write_throughput", self._card_labels["total_write_throughput"]),
            ("total_io_throughput", self._card_labels["total_io_throughput"]),
            ("io_bound_count", self._card_labels["io_bound_count"]),
            ("cpu_bound_count", self._card_labels["cpu_bound_count"]),
            ("balanced_count", self._card_labels["balanced_count"]),
            ("active_anomalies", self._card_labels["active_anomalies"]),
        ):
            value = overview.get(key, "—")
            if key in ("total_read_throughput", "total_write_throughput", "total_io_throughput"):
                value = format_bytes_per_sec(value)
            label.config(text=str(value))

        # Highlight the anomaly card color.
        anomaly_card = self._card_labels["active_anomalies"]
        if overview.get("active_anomalies", 0) > 0:
            anomaly_card.configure(style="IOPulse.Warn.TLabel")
        else:
            anomaly_card.configure(style="IOPulse.BigNum.TLabel")

        # --- Section B process table ---
        rows = prepare_process_table_data(metrics_list, classifications, health_map)
        self._last_rows = rows
        self.tree_processes.delete(*self.tree_processes.get_children())
        for row in rows:
            self.tree_processes.insert(
                "",
                "end",
                iid=str(row["pid_raw"]),
                values=(
                    row["pid"], row["name"], row["cpu"], row["read_rate"],
                    row["write_rate"], row["total_io_rate"], row["classification"],
                    row["confidence"], row["status"],
                ),
            )

        # --- Section E anomaly table ---
        anomalies = prepare_anomaly_display_data(pids, health_results, {
            int(c["pid"]): c for c in classifications if "pid" in c
        })
        self._last_anomalies = anomalies
        self.tree_anomalies.delete(*self.tree_anomalies.get_children())
        self.lbl_anomaly_empty.grid_remove()
        if anomalies:
            for index, anomaly in enumerate(anomalies):
                self.tree_anomalies.insert(
                    "",
                    "end",
                    iid=f"anom-{index}",
                    values=(
                        anomaly["pid"], anomaly["process_name"],
                        anomaly["severity"], anomaly["type"],
                    ),
                )
        else:
            self.lbl_anomaly_empty.grid()

        # --- Section C scatter plot ---
        self._render_scatter(classifications)
        # --- Section D throughput graph ---
        self._render_throughput()
        # --- Section F scheduling table ---
        self._render_scheduling(scheduling)

        # Status line
        if metrics_list:
            self.lbl_status.config(
                text=(
                    f"Monitoring {len(metrics_list)} processes @ "
                    f"{self._interval_ms} ms — {overview['active_anomalies']} active "
                    f"anomal{(lambda: 'y' if overview['active_anomalies'] == 1 else 'ies')()}"
                )
            )
        else:
            self.lbl_status.config(text="Monitoring… waiting for accessible process telemetry.")

    # ---------------------------------------------------------------
    # Graph rendering (Sections C & D)
    # ---------------------------------------------------------------

    def _clear_axis(self, axis) -> None:
        axis.clear()
        axis.set_facecolor(COLORS["bg_card"])
        axis.tick_params(colors=COLORS["text_muted"], labelsize=7)
        for spine in axis.spines.values():
            spine.set_color(COLORS["header_bg"])
        axis.grid(True, alpha=0.15, color=COLORS["text_muted"])

    def _render_scatter(self, classifications: List[Dict[str, Any]]) -> None:
        scatter = prepare_classification_scatter_data(classifications)
        figure = self.scatter_figure
        figure.clear()
        axis = figure.add_subplot(111)
        self._clear_axis(axis)
        axis.set_xlabel("CPU %", color=COLORS["text_muted"], fontsize=8)
        axis.set_ylabel("I/O bytes/sec", color=COLORS["text_muted"], fontsize=8)

        if scatter["total_points"] == 0:
            axis.text(
                0.5, 0.5, "Waiting for telemetry…",
                transform=axis.transAxes, ha="center", va="center",
                color=COLORS["text_muted"], fontsize=10,
            )
        else:
            legend_handles = {}
            for key, point_set in scatter["series"].items():
                style = CLASSIFICATION_STYLE.get(key, CLASSIFICATION_STYLE["IDLE"])
                handle = axis.scatter(
                    point_set["x"], point_set["y"],
                    c=style["color"], marker=style["marker"], s=32,
                    alpha=0.85, label=style["label"],
                )
                legend_handles[style["label"]] = handle
            axis.legend(
                handles=list(legend_handles.values()),
                loc="upper right", fontsize=7,
                facecolor=COLORS["bg_surface"],
                edgecolor=COLORS["header_bg"],
                labelcolor=COLORS["text_primary"],
            )
        figure.tight_layout()
        self.scatter_canvas.draw()

    def _render_throughput(self) -> None:
        figure = self.thr_figure
        figure.clear()
        axis = figure.add_subplot(111)
        self._clear_axis(axis)

        # Aggregate the most recent snapshot for each monitored process.
        series = self._aggregate_throughput_series()
        axis.set_xlabel("Sample", color=COLORS["text_muted"], fontsize=8)
        axis.set_ylabel("Bytes/sec", color=COLORS["text_muted"], fontsize=8)

        if not series or not series.get("total"):
            axis.text(
                0.5, 0.5, "Waiting for telemetry…",
                transform=axis.transAxes, ha="center", va="center",
                color=COLORS["text_muted"], fontsize=10,
            )
            figure.tight_layout()
            self.thr_canvas.draw()
            return

        x = list(range(len(series["read"])))
        axis.plot(x, series["read"], color=COLORS["accent_blue"], label="Read", linewidth=1.4)
        axis.plot(x, series["write"], color=COLORS["accent_peach"], label="Write", linewidth=1.4)
        axis.plot(x, series["total"], color=COLORS["accent_green"], label="Total", linewidth=1.6)
        axis.legend(
            loc="upper left", fontsize=7,
            facecolor=COLORS["bg_surface"],
            edgecolor=COLORS["header_bg"],
            labelcolor=COLORS["text_primary"],
        )
        figure.tight_layout()
        self.thr_canvas.draw()

    def _aggregate_throughput_series(self) -> Dict[str, List[float]]:
        """Combine all per-process histories into three aggregate series."""
        combined_read: List[float] = []
        combined_write: List[float] = []
        combined_total: List[float] = []

        for history in self._history.values():
            for entry in history:
                if not isinstance(entry, dict):
                    continue
                combined_read.append(_safe_float(entry.get("read_bytes_per_sec")))
                combined_write.append(_safe_float(entry.get("write_bytes_per_sec")))
                combined_total.append(_safe_float(entry.get("total_io_bytes_per_sec")))

        return {"read": combined_read, "write": combined_write, "total": combined_total}

    # ---------------------------------------------------------------
    # Section F scheduling rendering
    # ---------------------------------------------------------------

    def _run_scheduling(self) -> None:
        try:
            metrics_list = getattr(self, "_metrics_list", [])
            if not metrics_list:
                messagebox.showinfo(
                    "IOPulse — Disk Scheduling",
                    "No process I/O telemetry available yet. "
                    "Start monitoring and try again.",
                )
                self._scheduling = None
                self._render_scheduling(None)
                return
            # Reuses the Phase 4 bridge — no logic lives here.
            self._scheduling = analyze_process_io_scheduling(metrics_list)
            self._render_scheduling(self._scheduling)
        except Exception as exc:  # pragma: no cover - defensive for GUI
            messagebox.showerror(
                "IOPulse — Disk Scheduling",
                f"Could not analyse scheduling: {exc}",
            )

    def _render_scheduling(self, scheduling: Optional[Dict[str, Any]]) -> None:
        data = prepare_scheduling_display_data(scheduling)
        self._last_scheduling = data
        self.tree_scheduling.delete(*self.tree_scheduling.get_children())

        for name, info in data["algorithms"].items():
            self.tree_scheduling.insert(
                "",
                "end",
                values=(name, info["request_count"], info["head_movement"]),
            )

        self.lbl_simulation_note.config(
            text=data["simulation_note"]
            or "Simulated disk request workload derived from observed process I/O activity."
        )
        self.lbl_recommendation.config(text=f"Recommended: {data['recommended']}")
        self.lbl_recommendation_reason.config(text=data["recommendation_reason"])

    # ---------------------------------------------------------------
    # Explainability (Section G)
    # ---------------------------------------------------------------

    def _set_explanation(self, text: str) -> None:
        self.explanation.configure(state="normal")
        self.explanation.delete("1.0", "end")
        self.explanation.insert("1.0", text)
        self.explanation.configure(state="disabled")

    def _on_process_selected(self, _event=None) -> None:
        selection = self.tree_processes.selection()
        if not selection:
            return
        pid = selection[0]
        for row in self._last_rows:
            if str(row["pid_raw"]) == str(pid):
                explanation = prepare_explanation("classification", {
                    "classification": row["classification_raw"],
                    "cpu_percent": row["cpu_raw"],
                    "total_io_bytes_per_sec": row["total_io_rate_raw"],
                    "cpu_score": None,
                    "io_score": None,
                    "reason": row["reason"],
                })
                self._set_explanation(
                    f"Why is this process classified {row['classification']}?\n{explanation}"
                )
                return
        self._set_explanation("Process no longer available — it may have exited.")

    def _on_anomaly_selected(self, _event=None) -> None:
        selection = self.tree_anomalies.selection()
        if not selection:
            return
        index_str = selection[0]
        if index_str.startswith("anom-"):
            try:
                index = int(index_str.split("-", 1)[1])
            except ValueError:
                return
            if index < len(self._last_anomalies):
                anomaly = self._last_anomalies[index]
                self._set_explanation(prepare_explanation("anomaly", {
                    "type": anomaly["type"],
                    "severity": anomaly["severity"].lower(),
                    "reason": anomaly["reason"],
                }))

    # ---------------------------------------------------------------
    # Controls (Section H)
    # ---------------------------------------------------------------

    def toggle_running(self) -> None:
        self._running = not self._running
        self.btn_toggle.config(text="Resume" if not self._running else "Pause")
        if self._running:
            self.refresh_now()

    def apply_interval(self) -> None:
        ok, message = validate_refresh_interval(self.entry_interval.get())
        if not ok:
            messagebox.showwarning("IOPulse — Refresh Interval", message)
            self.entry_interval.delete(0, "end")
            self.entry_interval.insert(0, str(self.DEFAULT_INTERVAL_MS))
            return
        self._interval_ms = int(self.entry_interval.get().strip())
        self.refresh_now()

    def refresh_now(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        self._refresh_once()
        if self._running:
            self._schedule_refresh()

    def _refresh_once(self) -> None:
        """Collect and re-render once. Never raises into the UI loop."""
        try:
            self._collect_latest()
            self._render()
        except Exception:  # pragma: no cover - defensive for the GUI loop
            pass

    def _schedule_refresh(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self._after_id = self.after(self._interval_ms, self._on_tick)

    def _on_tick(self) -> None:
        self._after_id = None
        if not self._running:
            return
        self._refresh_once()
        self._schedule_refresh()

    def stop(self) -> None:
        self._running = False
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None