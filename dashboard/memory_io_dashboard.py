"""
dashboard/memory_io_dashboard.py – Memory & I/O Dashboard (Phase 5)
OS Sentinel – Teammate B (Memory & I/O Subsystem)

=== PURPOSE ===
A Tkinter + matplotlib GUI dashboard that visualizes the output of every
Phase 1–4 module.  This file contains ZERO algorithm logic — it only
calls existing modules, receives their structured dictionaries, and
renders the results.

=== ARCHITECTURE ===
    Existing modules  →  structured dicts  →  this dashboard  →  visuals

=== SECTIONS ===
    Tab 1 – Memory Overview:   Live monitor + RAM/Swap graph + Anomaly alerts
    Tab 2 – Process Memory:    Per-process memory table
    Tab 3 – Page Replacement:  FIFO / LRU / Optimal visualizer
    Tab 4 – Disk & Fragmentation: Disk scheduling + fragmentation info

=== LAUNCH ===
    python main.py          (launches dashboard)
    python main.py --cli    (old terminal demo)
"""

import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque
import time

import matplotlib
matplotlib.use("TkAgg")  # Must be set before importing pyplot
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ---------------------------------------------------------------------------
# Import existing Phase 1–4 modules (NO algorithm logic is duplicated here)
# ---------------------------------------------------------------------------
from memory.monitor import get_system_memory, get_process_memory
from memory.page_replacement import fifo, lru, optimal, compare_algorithms
from memory.fragmentation import (
    calculate_internal_fragmentation,
    calculate_external_fragmentation,
)
from disk_io.fcfs import fcfs
from disk_io.sstf import sstf
from disk_io.scan import scan
from disk_io.cscan import cscan
from intelligence.memory_anomaly import analyze_memory_health


# ===================================================================
# Color palette & style constants
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
    "hit_green":    "#2d5a3d",
    "fault_red":    "#5a2d3d",
    "header_bg":    "#45475a",
}

FONT_FAMILY = "Segoe UI"
FONT_TITLE  = (FONT_FAMILY, 16, "bold")
FONT_HEADER = (FONT_FAMILY, 12, "bold")
FONT_BODY   = (FONT_FAMILY, 10)
FONT_MONO   = ("Consolas", 10)
FONT_SMALL  = (FONT_FAMILY, 9)
FONT_BIG    = (FONT_FAMILY, 22, "bold")


# ===================================================================
# Input parsing helpers (used by dashboard, tested in test_dashboard.py)
# ===================================================================

def parse_page_string(text: str) -> list:
    """Parse a space/comma-separated string into a list of integers.

    Raises ValueError with a user-friendly message on bad input.
    """
    text = text.strip()
    if not text:
        raise ValueError("Page reference string cannot be empty.")

    # Accept both commas and spaces as delimiters.
    parts = text.replace(",", " ").split()
    pages = []
    for part in parts:
        try:
            pages.append(int(part))
        except ValueError:
            raise ValueError(
                f"'{part}' is not a valid integer.  "
                f"Enter space- or comma-separated page numbers."
            )
    return pages


def parse_request_queue(text: str) -> list:
    """Parse a space/comma-separated string into a list of non-negative ints.

    Raises ValueError with a user-friendly message on bad input.
    """
    text = text.strip()
    if not text:
        raise ValueError("Request queue cannot be empty.")

    parts = text.replace(",", " ").split()
    reqs = []
    for part in parts:
        try:
            val = int(part)
        except ValueError:
            raise ValueError(
                f"'{part}' is not a valid integer.  "
                f"Enter space- or comma-separated cylinder numbers."
            )
        if val < 0:
            raise ValueError(
                f"Cylinder number {val} is negative.  "
                f"All cylinder numbers must be ≥ 0."
            )
        reqs.append(val)
    return reqs


def parse_positive_int(text: str, name: str) -> int:
    """Parse a string into a positive integer.

    Raises ValueError with a user-friendly message on bad input.
    """
    text = text.strip()
    if not text:
        raise ValueError(f"{name} cannot be empty.")
    try:
        val = int(text)
    except ValueError:
        raise ValueError(f"{name} must be a whole number, got '{text}'.")
    if val <= 0:
        raise ValueError(f"{name} must be positive, got {val}.")
    return val


def parse_non_negative_int(text: str, name: str) -> int:
    """Parse a string into a non-negative integer.

    Raises ValueError with a user-friendly message on bad input.
    """
    text = text.strip()
    if not text:
        raise ValueError(f"{name} cannot be empty.")
    try:
        val = int(text)
    except ValueError:
        raise ValueError(f"{name} must be a whole number, got '{text}'.")
    if val < 0:
        raise ValueError(f"{name} must be non-negative, got {val}.")
    return val


# ===================================================================
# Main Dashboard Application
# ===================================================================

class MemoryIODashboard:
    """Tkinter dashboard for OS Sentinel – Memory & I/O subsystem."""

    # Refresh intervals (milliseconds)
    MEMORY_REFRESH_MS   = 2000
    PROCESS_REFRESH_MS  = 5000
    HISTORY_MAX_LEN     = 60      # data points kept for the graph

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("OS Sentinel — Memory & I/O Dashboard")
        self.root.configure(bg=COLORS["bg_dark"])
        self.root.geometry("1100x780")
        self.root.minsize(900, 650)

        # History deques for the live graph
        self.ram_history  = deque(maxlen=self.HISTORY_MAX_LEN)
        self.swap_history = deque(maxlen=self.HISTORY_MAX_LEN)
        self.time_history = deque(maxlen=self.HISTORY_MAX_LEN)
        self._start_time  = time.time()

        # Periodic timer IDs (so we can cancel on close)
        self._mem_timer_id  = None
        self._proc_timer_id = None

        # Sorting state for the process table
        self._sort_col     = "memory_percent"
        self._sort_reverse = True

        self._configure_styles()
        self._build_ui()
        self._start_periodic_updates()

        # Graceful shutdown
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------
    # Style configuration
    # ---------------------------------------------------------------

    def _configure_styles(self):
        """Apply the dark colour scheme to ttk widgets."""
        style = ttk.Style()
        style.theme_use("clam")

        # Notebook (tabs)
        style.configure("TNotebook", background=COLORS["bg_dark"],
                        borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=COLORS["bg_surface"],
                        foreground=COLORS["text_muted"],
                        padding=[14, 6],
                        font=FONT_BODY)
        style.map("TNotebook.Tab",
                  background=[("selected", COLORS["accent_blue"])],
                  foreground=[("selected", COLORS["bg_dark"])])

        # Frames
        style.configure("Dark.TFrame", background=COLORS["bg_dark"])
        style.configure("Card.TFrame", background=COLORS["bg_card"])
        style.configure("Surface.TFrame", background=COLORS["bg_surface"])

        # Labels
        style.configure("Dark.TLabel", background=COLORS["bg_dark"],
                        foreground=COLORS["text_primary"], font=FONT_BODY)
        style.configure("Card.TLabel", background=COLORS["bg_card"],
                        foreground=COLORS["text_primary"], font=FONT_BODY)
        style.configure("Muted.TLabel", background=COLORS["bg_card"],
                        foreground=COLORS["text_muted"], font=FONT_SMALL)
        style.configure("Title.TLabel", background=COLORS["bg_dark"],
                        foreground=COLORS["accent_blue"], font=FONT_TITLE)
        style.configure("Header.TLabel", background=COLORS["bg_dark"],
                        foreground=COLORS["text_primary"], font=FONT_HEADER)
        style.configure("BigNum.TLabel", background=COLORS["bg_card"],
                        foreground=COLORS["accent_blue"], font=FONT_BIG)
        style.configure("StatLabel.TLabel", background=COLORS["bg_card"],
                        foreground=COLORS["text_muted"], font=FONT_SMALL)
        style.configure("Good.TLabel", background=COLORS["bg_card"],
                        foreground=COLORS["accent_green"], font=FONT_BODY)
        style.configure("Warn.TLabel", background=COLORS["bg_card"],
                        foreground=COLORS["warning"], font=FONT_BODY)
        style.configure("Error.TLabel", background=COLORS["bg_card"],
                        foreground=COLORS["error"], font=FONT_BODY)

        # Buttons
        style.configure("Accent.TButton",
                        background=COLORS["accent_blue"],
                        foreground=COLORS["bg_dark"],
                        font=FONT_BODY, padding=[12, 4])
        style.map("Accent.TButton",
                  background=[("active", COLORS["accent_green"])])

        # Entry
        style.configure("Dark.TEntry",
                        fieldbackground=COLORS["bg_surface"],
                        foreground=COLORS["text_primary"],
                        insertcolor=COLORS["text_primary"])

        # Combobox
        style.configure("Dark.TCombobox",
                        fieldbackground=COLORS["bg_surface"],
                        foreground=COLORS["text_primary"],
                        selectbackground=COLORS["accent_blue"],
                        selectforeground=COLORS["bg_dark"])
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", COLORS["bg_surface"])])

        # Treeview
        style.configure("Dark.Treeview",
                        background=COLORS["bg_surface"],
                        foreground=COLORS["text_primary"],
                        fieldbackground=COLORS["bg_surface"],
                        font=FONT_MONO,
                        rowheight=24)
        style.configure("Dark.Treeview.Heading",
                        background=COLORS["header_bg"],
                        foreground=COLORS["text_primary"],
                        font=(FONT_FAMILY, 10, "bold"))
        style.map("Dark.Treeview",
                  background=[("selected", COLORS["accent_blue"])],
                  foreground=[("selected", COLORS["bg_dark"])])

        # Progressbar
        style.configure("Ram.Horizontal.TProgressbar",
                        troughcolor=COLORS["bg_surface"],
                        background=COLORS["accent_blue"],
                        thickness=18)
        style.configure("Swap.Horizontal.TProgressbar",
                        troughcolor=COLORS["bg_surface"],
                        background=COLORS["accent_peach"],
                        thickness=18)

        # Separator
        style.configure("Dark.TSeparator", background=COLORS["header_bg"])

        # LabelFrame
        style.configure("Card.TLabelframe",
                        background=COLORS["bg_card"],
                        foreground=COLORS["accent_blue"],
                        font=FONT_HEADER)
        style.configure("Card.TLabelframe.Label",
                        background=COLORS["bg_card"],
                        foreground=COLORS["accent_blue"],
                        font=FONT_HEADER)

    # ---------------------------------------------------------------
    # UI construction
    # ---------------------------------------------------------------

    def _build_ui(self):
        """Assemble the entire dashboard."""
        # Title bar
        title_frame = ttk.Frame(self.root, style="Dark.TFrame")
        title_frame.pack(fill="x", padx=12, pady=(10, 2))
        ttk.Label(title_frame, text="🛡  OS SENTINEL",
                  style="Title.TLabel").pack(side="left")
        ttk.Label(title_frame, text="Memory & I/O Dashboard",
                  style="Dark.TLabel").pack(side="left", padx=(10, 0))

        ttk.Separator(self.root, orient="horizontal",
                      style="Dark.TSeparator").pack(fill="x", padx=12, pady=4)

        # Notebook (tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._build_tab_memory_overview()
        self._build_tab_process_memory()
        self._build_tab_page_replacement()
        self._build_tab_disk_and_fragmentation()

    # ---------------------------------------------------------------
    # TAB 1 — Memory Overview (Sections 1, 2, 7)
    # ---------------------------------------------------------------

    def _build_tab_memory_overview(self):
        tab = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(tab, text="  Memory Overview  ")

        # ----- Section 1: Live memory stats -----
        ttk.Label(tab, text="Live Memory Monitor",
                  style="Header.TLabel").pack(anchor="w", padx=10, pady=(10, 4))

        stats_frame = ttk.Frame(tab, style="Card.TFrame")
        stats_frame.pack(fill="x", padx=10, pady=(0, 6))

        # RAM card
        ram_card = ttk.Frame(stats_frame, style="Card.TFrame")
        ram_card.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)

        ttk.Label(ram_card, text="RAM", style="StatLabel.TLabel").pack(anchor="w")
        self.lbl_ram_pct = ttk.Label(ram_card, text="—%", style="BigNum.TLabel")
        self.lbl_ram_pct.pack(anchor="w")
        self.pb_ram = ttk.Progressbar(ram_card, length=200, maximum=100,
                                      style="Ram.Horizontal.TProgressbar")
        self.pb_ram.pack(fill="x", pady=(2, 4))
        self.lbl_ram_detail = ttk.Label(ram_card, text="", style="Muted.TLabel")
        self.lbl_ram_detail.pack(anchor="w")

        # Swap card
        swap_card = ttk.Frame(stats_frame, style="Card.TFrame")
        swap_card.pack(side="left", fill="both", expand=True, padx=(4, 4), pady=8)

        ttk.Label(swap_card, text="SWAP", style="StatLabel.TLabel").pack(anchor="w")
        self.lbl_swap_pct = ttk.Label(swap_card, text="—%", style="BigNum.TLabel")
        self.lbl_swap_pct.pack(anchor="w")
        self.pb_swap = ttk.Progressbar(swap_card, length=200, maximum=100,
                                       style="Swap.Horizontal.TProgressbar")
        self.pb_swap.pack(fill="x", pady=(2, 4))
        self.lbl_swap_detail = ttk.Label(swap_card, text="", style="Muted.TLabel")
        self.lbl_swap_detail.pack(anchor="w")

        # Totals card
        totals_card = ttk.Frame(stats_frame, style="Card.TFrame")
        totals_card.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)

        ttk.Label(totals_card, text="TOTALS", style="StatLabel.TLabel").pack(anchor="w")
        self.lbl_total_ram = ttk.Label(totals_card, text="", style="Card.TLabel")
        self.lbl_total_ram.pack(anchor="w", pady=(4, 0))
        self.lbl_total_swap = ttk.Label(totals_card, text="", style="Card.TLabel")
        self.lbl_total_swap.pack(anchor="w")
        self.lbl_avail = ttk.Label(totals_card, text="", style="Card.TLabel")
        self.lbl_avail.pack(anchor="w")

        # ----- Bottom: graph (left) + alerts (right) -----
        bottom = ttk.Frame(tab, style="Dark.TFrame")
        bottom.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Section 2: memory graph
        graph_frame = ttk.Frame(bottom, style="Card.TFrame")
        graph_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))

        ttk.Label(graph_frame, text="  RAM & Swap Usage Over Time",
                  style="Card.TLabel").pack(anchor="w", pady=(6, 0))

        self.fig_mem = Figure(figsize=(5, 2.8), dpi=90,
                             facecolor=COLORS["bg_card"])
        self.ax_mem = self.fig_mem.add_subplot(111)
        self._style_axis(self.ax_mem, "Time (s)", "Usage %")
        self.canvas_mem = FigureCanvasTkAgg(self.fig_mem, master=graph_frame)
        self.canvas_mem.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)

        # Section 7: anomaly alerts
        alert_frame = ttk.Frame(bottom, style="Card.TFrame")
        alert_frame.pack(side="right", fill="both", expand=False, padx=(4, 0))
        alert_frame.configure(width=310)
        alert_frame.pack_propagate(False)

        ttk.Label(alert_frame, text="  Memory Anomaly Alerts",
                  style="Card.TLabel").pack(anchor="w", pady=(6, 4))

        self.alert_container = ttk.Frame(alert_frame, style="Card.TFrame")
        self.alert_container.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Initial "collecting data" message
        self.lbl_alert_status = ttk.Label(
            self.alert_container,
            text="✅  Collecting data…\n\nAnomalies will be shown\nonce enough observations\nare gathered.",
            style="Good.TLabel", wraplength=260, justify="left"
        )
        self.lbl_alert_status.pack(anchor="nw", pady=4)

    # ---------------------------------------------------------------
    # TAB 2 — Process Memory (Section 3)
    # ---------------------------------------------------------------

    def _build_tab_process_memory(self):
        tab = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(tab, text="  Process Memory  ")

        ttk.Label(tab, text="Per-Process Memory Table",
                  style="Header.TLabel").pack(anchor="w", padx=10, pady=(10, 4))
        ttk.Label(tab,
                  text="Top 20 processes by memory — click column headers to sort.  Refreshes every 5 s.",
                  style="Dark.TLabel").pack(anchor="w", padx=10, pady=(0, 6))

        # Treeview
        cols = ("pid", "name", "memory_percent", "memory_rss_mb")
        self.proc_tree = ttk.Treeview(
            tab, columns=cols, show="headings", style="Dark.Treeview", height=22
        )
        self.proc_tree.heading("pid",            text="PID",       command=lambda: self._sort_procs("pid"))
        self.proc_tree.heading("name",           text="Process",   command=lambda: self._sort_procs("name"))
        self.proc_tree.heading("memory_percent", text="Memory %",  command=lambda: self._sort_procs("memory_percent"))
        self.proc_tree.heading("memory_rss_mb",  text="RSS (MB)",  command=lambda: self._sort_procs("memory_rss_mb"))

        self.proc_tree.column("pid",            width=80,  anchor="e")
        self.proc_tree.column("name",           width=260, anchor="w")
        self.proc_tree.column("memory_percent", width=110, anchor="e")
        self.proc_tree.column("memory_rss_mb",  width=110, anchor="e")

        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=self.proc_tree.yview)
        self.proc_tree.configure(yscrollcommand=scrollbar.set)

        self.proc_tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 10))
        scrollbar.pack(side="right", fill="y", pady=(0, 10), padx=(0, 10))

        # Tag for alternating rows
        self.proc_tree.tag_configure("odd",  background=COLORS["bg_surface"])
        self.proc_tree.tag_configure("even", background=COLORS["bg_card"])

    # ---------------------------------------------------------------
    # TAB 3 — Page Replacement (Section 4)
    # ---------------------------------------------------------------

    def _build_tab_page_replacement(self):
        tab = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(tab, text="  Page Replacement  ")

        ttk.Label(tab, text="Page Replacement Visualizer",
                  style="Header.TLabel").pack(anchor="w", padx=10, pady=(10, 4))

        # --- Input area ---
        input_frame = ttk.Frame(tab, style="Card.TFrame")
        input_frame.pack(fill="x", padx=10, pady=(0, 6))

        row1 = ttk.Frame(input_frame, style="Card.TFrame")
        row1.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(row1, text="Pages:", style="Card.TLabel").pack(side="left")
        self.ent_pages = tk.Entry(row1, width=40, bg=COLORS["bg_surface"],
                                  fg=COLORS["text_primary"],
                                  insertbackground=COLORS["text_primary"],
                                  font=FONT_MONO, relief="flat")
        self.ent_pages.pack(side="left", padx=(6, 16))
        self.ent_pages.insert(0, "1 2 3 1 4 5 2 1")

        ttk.Label(row1, text="Frames:", style="Card.TLabel").pack(side="left")
        self.ent_frames = tk.Entry(row1, width=6, bg=COLORS["bg_surface"],
                                   fg=COLORS["text_primary"],
                                   insertbackground=COLORS["text_primary"],
                                   font=FONT_MONO, relief="flat")
        self.ent_frames.pack(side="left", padx=(6, 16))
        self.ent_frames.insert(0, "3")

        ttk.Label(row1, text="Algorithm:", style="Card.TLabel").pack(side="left")
        self.cmb_page_algo = ttk.Combobox(
            row1, values=["FIFO", "LRU", "Optimal", "Compare All"],
            state="readonly", width=14, style="Dark.TCombobox"
        )
        self.cmb_page_algo.pack(side="left", padx=(6, 16))
        self.cmb_page_algo.current(0)

        btn_run = ttk.Button(row1, text="▶  Run", style="Accent.TButton",
                             command=self._run_page_replacement)
        btn_run.pack(side="left")

        # --- Results summary ---
        self.page_result_frame = ttk.Frame(tab, style="Card.TFrame")
        self.page_result_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.lbl_page_summary = ttk.Label(
            self.page_result_frame,
            text="  Enter a page reference string and click Run.",
            style="Card.TLabel"
        )
        self.lbl_page_summary.pack(anchor="w", padx=8, pady=6)

        # --- Step-by-step table ---
        self.page_table_frame = ttk.Frame(tab, style="Dark.TFrame")
        self.page_table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Will be populated after a run
        self.page_tree = None

    # ---------------------------------------------------------------
    # TAB 4 — Disk Scheduling + Fragmentation (Sections 5 & 6)
    # ---------------------------------------------------------------

    def _build_tab_disk_and_fragmentation(self):
        tab = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(tab, text="  Disk & Fragmentation  ")

        # Scrollable canvas for this tab (it has a lot of content)
        canvas = tk.Canvas(tab, bg=COLORS["bg_dark"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        self.disk_tab_inner = ttk.Frame(canvas, style="Dark.TFrame")

        self.disk_tab_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.disk_tab_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind mousewheel for scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        inner = self.disk_tab_inner

        # ----- Section 5: Disk Scheduling -----
        ttk.Label(inner, text="Disk Scheduling Visualizer",
                  style="Header.TLabel").pack(anchor="w", padx=10, pady=(10, 4))

        disk_input = ttk.Frame(inner, style="Card.TFrame")
        disk_input.pack(fill="x", padx=10, pady=(0, 4))

        r1 = ttk.Frame(disk_input, style="Card.TFrame")
        r1.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(r1, text="Requests:", style="Card.TLabel").pack(side="left")
        self.ent_disk_reqs = tk.Entry(r1, width=40, bg=COLORS["bg_surface"],
                                      fg=COLORS["text_primary"],
                                      insertbackground=COLORS["text_primary"],
                                      font=FONT_MONO, relief="flat")
        self.ent_disk_reqs.pack(side="left", padx=(6, 16))
        self.ent_disk_reqs.insert(0, "98 183 37 122 14 124 65 67")

        ttk.Label(r1, text="Head:", style="Card.TLabel").pack(side="left")
        self.ent_disk_head = tk.Entry(r1, width=6, bg=COLORS["bg_surface"],
                                      fg=COLORS["text_primary"],
                                      insertbackground=COLORS["text_primary"],
                                      font=FONT_MONO, relief="flat")
        self.ent_disk_head.pack(side="left", padx=(6, 16))
        self.ent_disk_head.insert(0, "53")

        r2 = ttk.Frame(disk_input, style="Card.TFrame")
        r2.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Label(r2, text="Disk Size:", style="Card.TLabel").pack(side="left")
        self.ent_disk_size = tk.Entry(r2, width=6, bg=COLORS["bg_surface"],
                                      fg=COLORS["text_primary"],
                                      insertbackground=COLORS["text_primary"],
                                      font=FONT_MONO, relief="flat")
        self.ent_disk_size.pack(side="left", padx=(6, 16))
        self.ent_disk_size.insert(0, "200")

        ttk.Label(r2, text="Direction:", style="Card.TLabel").pack(side="left")
        self.cmb_disk_dir = ttk.Combobox(
            r2, values=["right", "left"], state="readonly",
            width=8, style="Dark.TCombobox"
        )
        self.cmb_disk_dir.pack(side="left", padx=(6, 16))
        self.cmb_disk_dir.current(0)

        ttk.Label(r2, text="Algorithm:", style="Card.TLabel").pack(side="left")
        self.cmb_disk_algo = ttk.Combobox(
            r2, values=["FCFS", "SSTF", "SCAN", "C-SCAN"],
            state="readonly", width=10, style="Dark.TCombobox"
        )
        self.cmb_disk_algo.pack(side="left", padx=(6, 16))
        self.cmb_disk_algo.current(0)

        btn_disk = ttk.Button(r2, text="▶  Run", style="Accent.TButton",
                              command=self._run_disk_scheduling)
        btn_disk.pack(side="left")

        # Disk results summary
        self.disk_result_frame = ttk.Frame(inner, style="Card.TFrame")
        self.disk_result_frame.pack(fill="x", padx=10, pady=(0, 4))
        self.lbl_disk_summary = ttk.Label(
            self.disk_result_frame,
            text="  Enter disk requests and click Run.",
            style="Card.TLabel"
        )
        self.lbl_disk_summary.pack(anchor="w", padx=8, pady=6)

        # Disk chart placeholder
        self.disk_chart_frame = ttk.Frame(inner, style="Card.TFrame")
        self.disk_chart_frame.pack(fill="x", padx=10, pady=(0, 8))
        self.canvas_disk = None  # will be created on first run

        ttk.Separator(inner, orient="horizontal",
                      style="Dark.TSeparator").pack(fill="x", padx=10, pady=8)

        # ----- Section 6: Fragmentation -----
        ttk.Label(inner, text="Fragmentation Analysis",
                  style="Header.TLabel").pack(anchor="w", padx=10, pady=(0, 4))

        # -- Internal fragmentation --
        int_frame = ttk.LabelFrame(inner, text="  Internal Fragmentation  ",
                                   style="Card.TLabelframe")
        int_frame.pack(fill="x", padx=10, pady=(0, 6))

        ttk.Label(int_frame,
                  text="Enter allocations as: requested,block_size  (one per line or semicolon-separated)",
                  style="Muted.TLabel").pack(anchor="w", padx=8, pady=(6, 2))

        self.txt_internal = tk.Text(int_frame, height=3, width=60,
                                    bg=COLORS["bg_surface"],
                                    fg=COLORS["text_primary"],
                                    insertbackground=COLORS["text_primary"],
                                    font=FONT_MONO, relief="flat")
        self.txt_internal.pack(fill="x", padx=8, pady=(0, 4))
        self.txt_internal.insert("1.0", "200,256; 300,512; 100,128")

        btn_int = ttk.Button(int_frame, text="Calculate Internal",
                             style="Accent.TButton",
                             command=self._run_internal_frag)
        btn_int.pack(anchor="w", padx=8, pady=(0, 4))

        self.lbl_int_result = ttk.Label(int_frame, text="", style="Card.TLabel",
                                        wraplength=700, justify="left")
        self.lbl_int_result.pack(anchor="w", padx=8, pady=(0, 8))

        # -- External fragmentation --
        ext_frame = ttk.LabelFrame(inner, text="  External Fragmentation  ",
                                   style="Card.TLabelframe")
        ext_frame.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Label(ext_frame,
                  text="Total memory size:",
                  style="Muted.TLabel").pack(anchor="w", padx=8, pady=(6, 2))

        self.ent_ext_total = tk.Entry(ext_frame, width=12,
                                      bg=COLORS["bg_surface"],
                                      fg=COLORS["text_primary"],
                                      insertbackground=COLORS["text_primary"],
                                      font=FONT_MONO, relief="flat")
        self.ent_ext_total.pack(anchor="w", padx=8)
        self.ent_ext_total.insert(0, "1024")

        ttk.Label(ext_frame,
                  text="Blocks as: start,size,alloc  (alloc = 1 or 0;  one per line or semicolon-separated)",
                  style="Muted.TLabel").pack(anchor="w", padx=8, pady=(6, 2))

        self.txt_external = tk.Text(ext_frame, height=3, width=60,
                                    bg=COLORS["bg_surface"],
                                    fg=COLORS["text_primary"],
                                    insertbackground=COLORS["text_primary"],
                                    font=FONT_MONO, relief="flat")
        self.txt_external.pack(fill="x", padx=8, pady=(0, 4))
        self.txt_external.insert("1.0", "0,200,1; 200,100,0; 300,150,1; 450,50,0; 500,200,1")

        btn_ext = ttk.Button(ext_frame, text="Calculate External",
                             style="Accent.TButton",
                             command=self._run_external_frag)
        btn_ext.pack(anchor="w", padx=8, pady=(0, 4))

        self.lbl_ext_result = ttk.Label(ext_frame, text="", style="Card.TLabel",
                                        wraplength=700, justify="left")
        self.lbl_ext_result.pack(anchor="w", padx=8, pady=(0, 8))

    # ---------------------------------------------------------------
    # Periodic update engine
    # ---------------------------------------------------------------

    def _start_periodic_updates(self):
        """Kick off the recurring memory and process refreshes."""
        self._refresh_memory()
        self._refresh_processes()

    def _refresh_memory(self):
        """Fetch system memory and update Sections 1, 2, and 7."""
        try:
            mem = get_system_memory()
        except Exception:
            self._mem_timer_id = self.root.after(
                self.MEMORY_REFRESH_MS, self._refresh_memory
            )
            return

        ram_pct  = mem["ram_percent"]
        swap_pct = mem["swap_percent"]

        # Section 1: live numbers
        self.lbl_ram_pct.configure(text=f"{ram_pct:.0f}%")
        self.pb_ram["value"] = min(ram_pct, 100)
        self.lbl_ram_detail.configure(
            text=f"Used: {mem['used_ram_mb']:.0f} MB  |  "
                 f"Available: {mem['available_ram_mb']:.0f} MB"
        )

        self.lbl_swap_pct.configure(text=f"{swap_pct:.0f}%")
        self.pb_swap["value"] = min(swap_pct, 100)
        self.lbl_swap_detail.configure(
            text=f"Used: {mem['used_swap_mb']:.0f} MB"
        )

        self.lbl_total_ram.configure(text=f"Total RAM:  {mem['total_ram_mb']:.0f} MB")
        self.lbl_total_swap.configure(text=f"Total Swap: {mem['total_swap_mb']:.0f} MB")
        self.lbl_avail.configure(text=f"Available:  {mem['available_ram_mb']:.0f} MB")

        # Section 2: update graph history
        elapsed = round(time.time() - self._start_time, 1)
        self.ram_history.append(ram_pct)
        self.swap_history.append(swap_pct)
        self.time_history.append(elapsed)
        self._redraw_memory_graph()

        # Section 7: anomaly check (need ≥ 5 observations)
        if len(self.ram_history) >= 5:
            self._update_anomaly_alerts(ram_pct, swap_pct)

        # Schedule next refresh
        self._mem_timer_id = self.root.after(
            self.MEMORY_REFRESH_MS, self._refresh_memory
        )

    def _refresh_processes(self):
        """Fetch per-process memory and update the table (Section 3)."""
        try:
            procs = get_process_memory(top_n=20)
        except Exception:
            self._proc_timer_id = self.root.after(
                self.PROCESS_REFRESH_MS, self._refresh_processes
            )
            return

        # Sort by current sort column
        reverse = self._sort_reverse
        key_col = self._sort_col
        try:
            procs.sort(
                key=lambda p: (p.get(key_col) or 0) if isinstance(p.get(key_col), (int, float)) else str(p.get(key_col, "")),
                reverse=reverse
            )
        except Exception:
            pass

        # Repopulate treeview
        self.proc_tree.delete(*self.proc_tree.get_children())
        for i, p in enumerate(procs):
            rss = f"{p['memory_rss_mb']:.2f}" if p["memory_rss_mb"] is not None else "N/A"
            tag = "odd" if i % 2 else "even"
            self.proc_tree.insert("", "end", values=(
                p["pid"], p["name"], f"{p['memory_percent']:.2f}%", rss
            ), tags=(tag,))

        self._proc_timer_id = self.root.after(
            self.PROCESS_REFRESH_MS, self._refresh_processes
        )

    # ---------------------------------------------------------------
    # Memory graph drawing
    # ---------------------------------------------------------------

    def _redraw_memory_graph(self):
        """Redraw the RAM/Swap usage plot."""
        ax = self.ax_mem
        ax.clear()
        self._style_axis(ax, "Time (s)", "Usage %")

        times = list(self.time_history)
        ram   = list(self.ram_history)
        swap  = list(self.swap_history)

        if times:
            ax.plot(times, ram,  color=COLORS["accent_blue"],
                    linewidth=1.8, label="RAM %")
            ax.fill_between(times, ram, alpha=0.15,
                            color=COLORS["accent_blue"])
            ax.plot(times, swap, color=COLORS["accent_peach"],
                    linewidth=1.8, label="Swap %", linestyle="--")

        ax.set_ylim(0, 105)
        ax.legend(loc="upper left", fontsize=8,
                  facecolor=COLORS["bg_card"],
                  edgecolor=COLORS["header_bg"],
                  labelcolor=COLORS["text_primary"])
        self.fig_mem.tight_layout(pad=1.2)
        self.canvas_mem.draw_idle()

    # ---------------------------------------------------------------
    # Anomaly alert update
    # ---------------------------------------------------------------

    def _update_anomaly_alerts(self, ram_pct: float, swap_pct: float):
        """Run the anomaly detector and display alerts (Section 7)."""
        try:
            result = analyze_memory_health(
                usage_history=list(self.ram_history),
                current_memory_pct=ram_pct,
                current_page_fault_rate=0.0,  # We don't have real page-fault data
                swap_usage_pct=swap_pct,
            )
        except Exception:
            return

        # Clear old alerts
        for widget in self.alert_container.winfo_children():
            widget.destroy()

        leak   = result["memory_leak"]
        thrash = result["thrashing"]

        if not result["any_anomaly"]:
            ttk.Label(
                self.alert_container,
                text="✅  No anomalies detected.\n\n"
                     f"Memory trend: stable\n"
                     f"Observations: {leak.get('num_observations', '—')}",
                style="Good.TLabel", wraplength=260, justify="left"
            ).pack(anchor="nw", pady=4)
            return

        # Memory leak alert
        if leak["anomaly"]:
            sev = leak["severity"]
            style = "Error.TLabel" if sev in ("critical", "high") else "Warn.TLabel"
            ttk.Label(
                self.alert_container,
                text=f"⚠  Possible Memory Leak\n"
                     f"   Severity: {sev.upper()}\n"
                     f"   {leak['reason']}\n"
                     f"   Increase: {leak['total_increase']:.2f}  |  "
                     f"Rising: {leak['increasing_pct']}%",
                style=style, wraplength=260, justify="left"
            ).pack(anchor="nw", pady=(4, 8))

        # Thrashing alert
        if thrash["anomaly"]:
            sev = thrash["severity"]
            style = "Error.TLabel" if sev in ("critical", "high") else "Warn.TLabel"
            ttk.Label(
                self.alert_container,
                text=f"⚠  Possible Thrashing\n"
                     f"   Severity: {sev.upper()}\n"
                     f"   {thrash['reason']}",
                style=style, wraplength=260, justify="left"
            ).pack(anchor="nw", pady=(4, 8))

        # High memory warning (non-anomaly but elevated)
        if not leak["anomaly"] and not thrash["anomaly"]:
            if ram_pct >= 80:
                ttk.Label(
                    self.alert_container,
                    text=f"⚠  High Memory Usage\n"
                         f"   RAM is at {ram_pct:.1f}%\n"
                         f"   Monitor closely.",
                    style="Warn.TLabel", wraplength=260, justify="left"
                ).pack(anchor="nw", pady=4)

    # ---------------------------------------------------------------
    # Page Replacement (Section 4) – Run handler
    # ---------------------------------------------------------------

    def _run_page_replacement(self):
        """Validate input, call existing algorithm, display results."""
        # Parse inputs
        try:
            pages = parse_page_string(self.ent_pages.get())
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))
            return

        try:
            num_frames = parse_positive_int(self.ent_frames.get(), "Frames")
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))
            return

        algo_name = self.cmb_page_algo.get()

        # Dispatch to existing module
        algo_map = {
            "FIFO":    fifo,
            "LRU":     lru,
            "Optimal": optimal,
        }

        if algo_name == "Compare All":
            results = compare_algorithms(pages, num_frames)
            self._show_page_comparison(results, num_frames)
        else:
            func = algo_map[algo_name]
            result = func(pages, num_frames)
            self._show_page_result(result, num_frames)

    def _show_page_result(self, result: dict, num_frames: int):
        """Display a single page-replacement result."""
        # Summary
        self.lbl_page_summary.configure(
            text=f"  {result['algorithm']}   |   "
                 f"Faults: {result['page_faults']}   |   "
                 f"Hits: {result['page_hits']}   |   "
                 f"Fault Rate: {result['fault_rate']:.2%}   |   "
                 f"Hit Rate: {result['hit_rate']:.2%}"
        )

        # Rebuild step table
        for w in self.page_table_frame.winfo_children():
            w.destroy()

        cols = ["Page"] + [f"Frame {i+1}" for i in range(num_frames)] + ["Result"]
        tree = ttk.Treeview(
            self.page_table_frame, columns=cols, show="headings",
            style="Dark.Treeview", height=min(len(result["steps"]), 18)
        )
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=80, anchor="center")
        tree.column("Page", width=60)
        tree.column("Result", width=80)

        tree.tag_configure("hit",   background=COLORS["hit_green"])
        tree.tag_configure("fault", background=COLORS["fault_red"])

        for step in result["steps"]:
            vals = [step["page"]]
            for fv in step["frames"]:
                vals.append(str(fv) if fv is not None else "—")
            vals.append("✓ Hit" if step["hit"] else "✗ Fault")
            tag = "hit" if step["hit"] else "fault"
            tree.insert("", "end", values=vals, tags=(tag,))

        sb = ttk.Scrollbar(self.page_table_frame, orient="vertical",
                           command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.page_tree = tree

    def _show_page_comparison(self, results: dict, num_frames: int):
        """Display comparison summary and the first algorithm's step table."""
        lines = []
        for algo, res in results.items():
            lines.append(
                f"{algo}:  Faults={res['page_faults']}  "
                f"Hits={res['page_hits']}  "
                f"Fault Rate={res['fault_rate']:.2%}  "
                f"Hit Rate={res['hit_rate']:.2%}"
            )
        self.lbl_page_summary.configure(text="  " + "   |   ".join(lines))

        # Show the first algorithm's step table
        first_result = list(results.values())[0]
        self._show_page_result(first_result, num_frames)
        # Re-set summary (since _show_page_result overrides it)
        self.lbl_page_summary.configure(text="  " + "\n  ".join(lines))

    # ---------------------------------------------------------------
    # Disk Scheduling (Section 5) – Run handler
    # ---------------------------------------------------------------

    def _run_disk_scheduling(self):
        """Validate input, call existing algorithm, display results + chart."""
        try:
            reqs = parse_request_queue(self.ent_disk_reqs.get())
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))
            return

        try:
            head = parse_non_negative_int(self.ent_disk_head.get(), "Initial Head")
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))
            return

        try:
            disk_size = parse_positive_int(self.ent_disk_size.get(), "Disk Size")
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))
            return

        direction = self.cmb_disk_dir.get()
        algo_name = self.cmb_disk_algo.get()

        # Dispatch to existing module
        try:
            if algo_name == "FCFS":
                result = fcfs(reqs, head, disk_size)
            elif algo_name == "SSTF":
                result = sstf(reqs, head, disk_size)
            elif algo_name == "SCAN":
                result = scan(reqs, head, disk_size, direction)
            elif algo_name == "C-SCAN":
                result = cscan(reqs, head, disk_size, direction)
            else:
                messagebox.showerror("Error", f"Unknown algorithm: {algo_name}")
                return
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))
            return

        # Summary
        dir_label = f" ({result.get('direction', '')})" if result.get("direction") else ""
        self.lbl_disk_summary.configure(
            text=f"  {result['algorithm']}{dir_label}   |   "
                 f"Total Head Movement: {result['total_head_movement']}   |   "
                 f"Avg Seek: {result['average_seek_distance']}   |   "
                 f"Order: {result['request_order']}"
        )

        # Draw disk movement chart
        self._draw_disk_chart(result)

    def _draw_disk_chart(self, result: dict):
        """Draw the disk-head movement path as a matplotlib chart."""
        # Clear old chart
        for w in self.disk_chart_frame.winfo_children():
            w.destroy()

        if not result["steps"]:
            return

        fig = Figure(figsize=(7, 3.2), dpi=90, facecolor=COLORS["bg_card"])
        ax = fig.add_subplot(111)
        self._style_axis(ax, "Request Sequence →", "Cylinder")

        # Build position sequence
        positions = [result["initial_head"]]
        for step in result["steps"]:
            positions.append(step["to"])

        x_vals = list(range(len(positions)))

        ax.plot(x_vals, positions, color=COLORS["accent_blue"],
                linewidth=1.8, marker="o", markersize=5,
                markerfacecolor=COLORS["accent_peach"],
                markeredgecolor=COLORS["accent_blue"])

        # Annotate head start
        ax.annotate("HEAD", (0, positions[0]),
                    textcoords="offset points", xytext=(8, 8),
                    fontsize=8, color=COLORS["accent_green"],
                    fontweight="bold")

        # Label each point
        for i, pos in enumerate(positions):
            ax.annotate(str(pos), (i, pos),
                        textcoords="offset points", xytext=(0, -14),
                        fontsize=7, color=COLORS["text_muted"],
                        ha="center")

        ax.set_ylim(-5, max(positions) + 20)
        fig.tight_layout(pad=1.5)

        canvas = FigureCanvasTkAgg(fig, master=self.disk_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="x", padx=6, pady=6)
        self.canvas_disk = canvas

    # ---------------------------------------------------------------
    # Fragmentation (Section 6)
    # ---------------------------------------------------------------

    def _run_internal_frag(self):
        """Parse input and call the existing internal fragmentation module."""
        raw = self.txt_internal.get("1.0", "end").strip()
        if not raw:
            messagebox.showerror("Input Error", "Please enter allocation data.")
            return

        # Parse: each entry is "requested,block_size"
        entries = [e.strip() for e in raw.replace("\n", ";").split(";") if e.strip()]
        allocations = []
        for i, entry in enumerate(entries):
            parts = entry.split(",")
            if len(parts) != 2:
                messagebox.showerror(
                    "Input Error",
                    f"Entry {i+1} ('{entry}') must be: requested,block_size"
                )
                return
            try:
                req = int(parts[0].strip())
                blk = int(parts[1].strip())
            except ValueError:
                messagebox.showerror(
                    "Input Error",
                    f"Entry {i+1}: both values must be integers."
                )
                return
            allocations.append({"requested": req, "block_size": blk})

        try:
            result = calculate_internal_fragmentation(allocations)
        except ValueError as e:
            messagebox.showerror("Calculation Error", str(e))
            return

        self.lbl_int_result.configure(
            text=f"Total Requested: {result['total_requested']}  |  "
                 f"Total Allocated: {result['total_allocated']}  |  "
                 f"Wasted: {result['wasted_memory']}  |  "
                 f"Fragmentation: {result['fragmentation_percentage']:.2f}%\n\n"
                 + "\n".join(
                     f"  Alloc {i+1}: req={a['requested']}, block={a['block_size']}, wasted={a['wasted']}"
                     for i, a in enumerate(result["allocations"])
                 )
        )

    def _run_external_frag(self):
        """Parse input and call the existing external fragmentation module."""
        try:
            total_mem = parse_positive_int(self.ent_ext_total.get(), "Total memory")
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))
            return

        raw = self.txt_external.get("1.0", "end").strip()
        if not raw:
            messagebox.showerror("Input Error", "Please enter block data.")
            return

        entries = [e.strip() for e in raw.replace("\n", ";").split(";") if e.strip()]
        blocks = []
        for i, entry in enumerate(entries):
            parts = entry.split(",")
            if len(parts) != 3:
                messagebox.showerror(
                    "Input Error",
                    f"Entry {i+1} ('{entry}') must be: start,size,allocated (0 or 1)"
                )
                return
            try:
                start = int(parts[0].strip())
                size  = int(parts[1].strip())
                alloc = int(parts[2].strip())
            except ValueError:
                messagebox.showerror(
                    "Input Error",
                    f"Entry {i+1}: all values must be integers."
                )
                return
            blocks.append({
                "start": start,
                "size": size,
                "allocated": bool(alloc),
            })

        try:
            result = calculate_external_fragmentation(total_mem, blocks)
        except ValueError as e:
            messagebox.showerror("Calculation Error", str(e))
            return

        self.lbl_ext_result.configure(
            text=f"Total Memory: {result['total_memory']}  |  "
                 f"Allocated: {result['allocated_memory']}  |  "
                 f"Free: {result['free_memory']}\n"
                 f"Free Blocks: {result['num_free_blocks']}  |  "
                 f"Largest Free Block: {result['largest_free_block']}  |  "
                 f"External Fragmentation: {result['fragmentation_percentage']:.2f}%\n\n"
                 + "\n".join(
                     f"  Free region: start={fb['start']}, size={fb['size']}"
                     for fb in result["free_blocks"]
                 )
        )

    # ---------------------------------------------------------------
    # Process table sorting
    # ---------------------------------------------------------------

    def _sort_procs(self, col: str):
        """Toggle sort order for the process table."""
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col
            self._sort_reverse = (col in ("memory_percent", "memory_rss_mb", "pid"))
        # Force immediate refresh
        self._refresh_processes()

    # ---------------------------------------------------------------
    # Matplotlib axis styling
    # ---------------------------------------------------------------

    def _style_axis(self, ax, xlabel: str, ylabel: str):
        """Apply consistent dark styling to a matplotlib axis."""
        ax.set_facecolor(COLORS["bg_card"])
        ax.set_xlabel(xlabel, color=COLORS["text_muted"], fontsize=9)
        ax.set_ylabel(ylabel, color=COLORS["text_muted"], fontsize=9)
        ax.tick_params(colors=COLORS["text_muted"], labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(COLORS["header_bg"])
        ax.grid(True, alpha=0.15, color=COLORS["text_muted"])

    # ---------------------------------------------------------------
    # Shutdown
    # ---------------------------------------------------------------

    def _on_close(self):
        """Cancel periodic timers and close the window."""
        if self._mem_timer_id:
            self.root.after_cancel(self._mem_timer_id)
        if self._proc_timer_id:
            self.root.after_cancel(self._proc_timer_id)
        self.root.destroy()


# ===================================================================
# Public launcher function
# ===================================================================

def launch_dashboard():
    """Create and launch the Memory & I/O dashboard."""
    root = tk.Tk()
    _app = MemoryIODashboard(root)
    root.mainloop()


if __name__ == "__main__":
    launch_dashboard()
