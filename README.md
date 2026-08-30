# IOPulse: Process-Aware I/O Behavior & Scheduling Intelligence Platform

IOPulse is a modular, explainable operating-systems learning platform that watches what processes actually do on disk — reads and writes, throughput, and I/O patterns — then classifies each process's CPU/I/O behavior, detects anomalies, and analyzes disk-scheduling cost. Every result carries a plain-language explanation, and everything runs in a live Tkinter + matplotlib dashboard.

> **OBSERVED DATA** comes from `psutil`'s **real** per-process CPU, memory, and disk I/O telemetry (bytes read/written, I/O counters, CPU time).
>
> **SIMULATED DATA** are disk-cylinder request workloads that IOPulse **derives deterministically from the observed telemetry** (e.g. using each process's read/write ratio and I/O activity to synthesize a cylinder sequence), then feeds to FCFS/SSTF/SCAN/C-SCAN.
>
> `psutil` does **not** report physical disk-cylinder positions. Cylinder positions are a simulation artifact used purely for scheduling analysis and are always labeled as simulated in the dashboard.

## What problem does it solve?

Most OS coursework treats disk I/O as raw bytes and never asks *which process* is doing the I/O or *why*. IOPulse answers the question "who is hammering the disk and is that behavior healthy?":

- A process suddenly reading at 6x its recent baseline is a **spike**.
- A previously-active process that has gone silent is an **I/O stall**.
- A process doing sustained high I/O may need attention.
- A process whose read/write mix abruptly shifts may have changed behavior.

It also connects the dots from *what* the process does to *how expensive the disk scheduling would be* — without ever touching the physical disk.

## Why does process I/O behavior matter?

- I/O-bound processes compete with CPU-bound ones for the same scheduler time and memory frames.
- Runaway or stalled writers degrade throughput and latency for the whole system.
- Understanding a process's read/write ratio and I/O intensity is the first step to tuning or isolating it.
- Disk scheduling cost (head movement) matters far more when you know which *processes* generate the conflicting requests.

## Architecture

```
IOPulse Dashboard (Tkinter + ttk + matplotlib)
      │
      ├── Process Monitor / CPU Scheduling / Deadlock / Anomaly / Alerts   (Process & Concurrency)
      └── Memory & I/O subsystem
            ├── Live Memory & Disk I/O telemetry          (psutil → OBSERVED)
            ├── CPU/I/O behavior classification           (rule-based)
            ├── I/O anomaly detection                     (spike / stall / sustained / ratio-shift)
            ├── Disk scheduling analysis                  (simulated: FCFS, SSTF, SCAN, C-SCAN)
            └── Explainability                            (plain-language reasons per result)
      │
      └── Alert Engine (bounded, normalized, report-only)
```

Rules:

- The dashboard is a **presentation layer only**. All scheduling, deadlock, monitoring, and anomaly logic lives in standalone modules that return structured dictionaries.
- Classification and anomaly detection are **rule-based and explainable** — no machine learning, no hidden models.
- Detectors are **report-only**. IOPulse never kills, throttles, or re-prioritizes processes.

### Live I/O telemetry

`intelligence/io_metrics.py` (`ProcessIOCollector`) samples per-process I/O counters from `psutil` over a sliding window and computes byte-per-second rates (`read_bytes_per_sec`, `write_bytes_per_sec`, `total_io_bytes_per_sec`) plus CPU%. Missing, vanished, or malformed processes are skipped safely; zero values are used when counters do not change.

### CPU/I/O behavior classification

`intelligence/io_classifier.py` (`ProcessIOClassifier`) labels each process as one of `CPU_BOUND`, `IO_BOUND`, `BALANCED`, or `IDLE` using simple, threshold-based rules over recent telemetry — with a confidence score and a human-readable reason.

### I/O anomaly detection

`intelligence/io_anomaly.py` (`analyze_io_health`) compares fresh observations against recent baselines and reports:

- **I/O spike** — current throughput far above the recent baseline
- **I/O stall** — previously active process gone quiet
- **Sustained high I/O** — continuous high throughput over many observations
- **Read/write ratio shift** — the R/W mix changed abruptly

### Disk scheduling analysis

`intelligence/io_disk_bridge.py` (`analyze_process_io_scheduling`) converts observed telemetry into a **simulated** single-cylinder request workload, then runs FCFS, SSTF, SCAN, and C-SCAN (the reference algorithms live in `disk_io/`) and reports head movement, average seek distance, per-algorithm steps, and a scheduling recommendation. Everything here is explicitly **simulated** in the UI.

### Explainability

Every component returns a `reason` plus supporting evidence. The dashboard's drill-down dialogs concatenate these into plain-language explanations showing exactly *why* a process was classified, why an anomaly fired, or why one scheduler beats another.

### Dashboard

`python -m dashboard.main` opens the unified desktop app:

1. **Process Monitor** – live process table (CPU%, memory%, status)
2. **CPU Scheduling** – FCFS, SJF, Priority, Round Robin with Gantt chart
3. **Deadlock** – Resource Allocation Graph and Banker's Algorithm
4. **Anomaly Detection** – runaway / zombie / starvation / CPU-I/O warnings
5. **Alerts** – normalized alert stream from all detectors
6. **IOPulse** – I/O telemetry overview, per-process I/O table, anomaly list, simulated scheduling summary, and drill-down explanations

The IOPulse tab refreshes on a timer (`after()`) so the Tkinter UI never blocks, and it degrades gracefully when telemetry is empty, missing, or malformed.

### Also included (support subsystems)

- **Memory & I/O**: live RAM/swap/process memory monitoring (`memory/monitor.py`), page replacement simulation (FIFO/LRU/Optimal, `memory/page_replacement.py`), fragmentation analysis (`memory/fragmentation.py`), memory anomaly detection (`intelligence/memory_anomaly.py`), and the standalone Memory & I/O dashboard (`dashboard/memory_io_dashboard.py`) reachable from the demo.
- **Process & Concurrency**: real-time process monitor, CPU scheduling algorithms, deadlock detection, and explainable process anomaly detection under `process_concurrency/`.

## Project Structure

```
IOPulse/
├── dashboard/                  # Tkinter GUI (presentation layer only)
│   ├── main.py                 # Unified dashboard + tab management
│   ├── iopulse_panel.py        # I/O telemetry, classification, anomaly,
│   │                           #   simulated scheduling + explanations
│   ├── process_panel.py        # Live process monitor view
│   ├── scheduling_panel.py     # CPU scheduling simulation + Gantt chart
│   ├── deadlock_panel.py       # RAG & Banker's Algorithm
│   ├── anomaly_panel.py        # Process anomaly warnings
│   ├── alert_engine.py         # Bounded alert normalization
│   ├── alert_panel.py          # Alert display
│   └── memory_io_dashboard.py  # Memory & I/O dashboard
├── intelligence/               # Detection & analysis (no ML, explainable)
│   ├── io_metrics.py           # Per-process I/O telemetry (OBSERVED)
│   ├── io_classifier.py        # CPU/I/O behavior classification
│   ├── io_anomaly.py           # Spike / stall / sustained / ratio-shift
│   ├── io_disk_bridge.py       # Telemetry → SIMULATED scheduling workload
│   └── memory_anomaly.py       # Memory leak & thrashing detection
├── disk_io/                    # Disk scheduling algorithms (SIMULATED)
│   ├── fcfs.py / sstf.py / scan.py / cscan.py
├── memory/                     # Memory monitoring & simulation
│   ├── monitor.py              # Live RAM / swap / process memory
│   ├── page_replacement.py     # FIFO, LRU, Optimal
│   └── fragmentation.py        # Internal & external fragmentation
├── process_concurrency/        # Process & concurrency modules
│   ├── process_monitor/        # Live process monitor
│   ├── scheduling/             # FCFS / SJF / Priority / Round Robin
│   ├── deadlock/               # RAG cycle detection, Banker's Algorithm
│   └── anomaly/                # Runaway / zombie / starvation detection
├── tests/                      # Unit tests (551)
├── main.py                     # Demo entry point (terminal + dashboard)
├── demo_disk_scheduling.py     # Disk scheduling terminal demo
├── requirements.txt
└── README.md
```

## Testing

The suite (`tests/`) covers scheduling algorithms, page replacement, disk scheduling, memory + process + I/O anomaly detection, dashboard input helpers, alert normalization, the IOPulse panel data pipelines, and a smoke test that the unified dashboard builds all six tabs.

```bash
# Standard library discoverer (no extra tools needed)
python -m unittest discover -v

# Or, if pytest is installed
pytest -q
```

## Installation

```bash
pip install -r requirements.txt
```

`requirements.txt` is intentionally minimal: `psutil` (real system telemetry) and `matplotlib` (graphs and Gantt charts). Everything else uses the Python standard library (Tkinter ships with Python; install `python3-tk` on Debian/Ubuntu if missing).

## Running the project

```bash
# Demo entry point (prints a live memory snapshot; --cli demo or GUI)
python main.py

# Unified IOPulse dashboard
python -m dashboard.main

# Standalone Memory & I/O dashboard
python -m dashboard.memory_io_dashboard

# Live process monitor terminal table
python -m process_concurrency.process_monitor.process_monitor --refresh 1

# Disk scheduling terminal demo
python demo_disk_scheduling.py
```

## Tech Stack

| Component    | Purpose                                      |
|--------------|----------------------------------------------|
| Python 3.8+  | Core language                                |
| psutil       | Real per-process CPU / memory / I/O telemetry |
| Tkinter      | GUI framework                                |
| matplotlib   | Graphs, visualizations, Gantt charts         |

## Notes

- Educational monitoring/simulation system. **It never kills, throttles, re-prioritizes, or modifies processes or system resources.**
- Alerts and drill-downs only report observations and suggest actions for human review.
- All simulation outputs (page replacement, disk scheduling cylinder positions, Gantt charts) are labeled as simulated where appropriate; live telemetry is the only observed data.
- Modules expose structured dictionaries/dataclasses, so the dashboard never re-implements algorithm logic.