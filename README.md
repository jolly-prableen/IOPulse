# OS Sentinel – Intelligent Process & Resource Management System

OS Sentinel is a modular OS learning project that implements explainable, rule-based process intelligence and system monitoring in phases. It combines two subsystems developed by the team:

- **Teammate A: Process & Concurrency** – Process monitoring, CPU scheduling, deadlock detection, anomaly detection, and alert engine
- **Teammate B: Memory & I/O** – Live memory monitoring, paging simulation, disk scheduling, memory anomaly detection, and Memory/I/O dashboard

## Project Structure

```
OS-Sentinel/
├── memory/                        # Memory monitoring & simulation (Teammate B)
│   ├── __init__.py
│   ├── monitor.py                 # Live RAM/swap/process monitoring
│   ├── page_replacement.py        # FIFO, LRU, Optimal algorithms
│   └── fragmentation.py           # Internal & external fragmentation
├── disk_io/                       # Disk scheduling algorithms (Teammate B)
│   ├── __init__.py
│   ├── fcfs.py
│   ├── sstf.py
│   ├── scan.py
│   └── cscan.py
├── intelligence/                  # Anomaly detection
│   ├── __init__.py
│   └── memory_anomaly.py          # Memory leak & thrashing detection (Teammate B)
├── process_concurrency/           # Process & concurrency modules (Teammate A)
│   ├── __init__.py
│   ├── process_monitor/
│   │   └── process_monitor.py     # Live process monitor
│   ├── scheduling/
│   │   ├── fcfs.py                # First-Come First-Served
│   │   ├── sjf.py                 # Shortest Job First
│   │   ├── priority.py            # Priority scheduling
│   │   ├── round_robin.py         # Round Robin
│   │   └── integration.py         # Common interface, metrics, Gantt chart
│   ├── deadlock/
│   │   ├── resource_allocation_graph.py  # DFS-based cycle detection
│   │   └── bankers_algorithm.py          # Safe-state detection
│   └── anomaly/
│       └── process_anomaly.py     # Runaway, zombie, starvation detection
├── dashboard/                     # Unified Tkinter desktop dashboard
│   ├── __init__.py
│   ├── main.py                    # Main app & tab management
│   ├── process_panel.py           # Live process monitor view (Teammate A)
│   ├── scheduling_panel.py        # CPU scheduling simulation (Teammate A)
│   ├── deadlock_panel.py          # RAG & Banker's Algorithm (Teammate A)
│   ├── anomaly_panel.py           # Process anomaly detection (Teammate A)
│   ├── alert_engine.py            # Bounded alert normalization (Teammate A)
│   ├── alert_panel.py             # Alert display (Teammate A)
│   └── memory_io_dashboard.py     # Memory & I/O dashboard (Teammate B)
├── tests/                         # Unit tests
├── main.py                        # Entry point / demo runner
├── requirements.txt
└── README.md
```

## Teammate A: Process & Concurrency Subsystem

### Phase 1: Real-Time Process Monitor

The monitor uses `psutil` to read live process information and renders a terminal table showing PID, Name, CPU%, Memory%, Priority, and Status. It refreshes every 1 second by default and safely skips inaccessible, missing, or zombie processes.

```bash
python -m process_concurrency.process_monitor.process_monitor --refresh 1
```

### Phase 2: FCFS Scheduling

Runs processes in arrival order and reports start time, completion time, turnaround time, and waiting time.

### Phase 3: SJF Scheduling

Selects the available process with the shortest burst time and reports scheduling metrics.

### Phase 4: Priority Scheduling

Selects processes according to their priority while preserving deterministic scheduling metrics.

### Phase 5: Round Robin Scheduling

Uses a configurable time quantum and returns execution order, completion, turnaround, and waiting metrics.

### Phase 6: Scheduling Metrics & Gantt Chart

The integration layer provides a common algorithm interface, calculates scheduling metrics, and generates a Gantt chart from actual execution segments.

### Phase 7: Resource Allocation Graph

Models process requests and resource allocations. DFS-based cycle detection reports potential deadlocks without modifying system resources.

### Phase 8: Banker's Algorithm

Checks whether a resource-allocation state is safe by computing Need = Maximum - Allocation and applying the standard Banker's Algorithm. Returns either a safe sequence or an unsafe warning.

### Phase 9: Process Anomaly Detection

Rule-based, explainable monitoring (no machine learning):

- **Runaway process detection** – Warns when CPU exceeds a threshold for consecutive observations
- **Zombie process detection** – Emits warnings for zombie-status processes
- **CPU starvation heuristic** – Conservative heuristic for sustained low-CPU active processes

Configurable thresholds:

```python
CPU_THRESHOLD = 90.0
CONSECUTIVE_HIGH_CPU = 5
HISTORY_LIMIT = 100
```

### Phase 10: Alert System

The Alert Engine (`dashboard/alert_engine.py`) provides a shared, bounded stream of explainable alerts. Supported severity levels: `INFO`, `WARNING`, `CRITICAL`. The system is report-only and never kills or throttles processes.

## Teammate B: Memory & I/O Subsystem

### Phase 1: Live Memory Monitoring

Monitors system memory (RAM, swap) and top memory-consuming processes, returning structured dictionaries for dashboard consumption.

### Phase 2: Memory Usage Graph

Visualizes memory usage over time using matplotlib.

### Phase 3: Per-Process Memory

Shows per-process memory breakdown.

### Phase 4: Page Replacement Simulation

Implements FIFO, LRU, and Optimal page replacement algorithms with step-by-step visualization.

### Phase 5: Disk Scheduling Simulation

Implements FCFS, SSTF, SCAN, and C-SCAN disk scheduling algorithms with head movement tracking.

### Phase 6: Memory Fragmentation

Analyzes internal and external fragmentation.

### Phase 7: Memory Anomaly Detection

Detects memory leaks and thrashing patterns.

## Unified Dashboard

The Tkinter desktop dashboard integrates both subsystems into a single window with five tabs:

1. **Process Monitor** – Live process information (Teammate A)
2. **CPU Scheduling** – FCFS, SJF, Priority, Round Robin with Gantt chart (Teammate A)
3. **Deadlock** – Resource Allocation Graph and Banker's Algorithm (Teammate A)
4. **Anomaly Detection** – Process anomaly warnings (Teammate A)
5. **Alerts** – Normalized alerts from all detectors (Teammate A)

The dashboard also includes the Memory & I/O dashboard panel from Teammate B.

### Architecture

```
GUI (Tkinter)
  ↓
Existing OS / Algorithm Modules
  ↓
Alert Engine where applicable
  ↓
OS / Scheduling / Deadlock / Detection logic
```

The GUI is a presentation layer. Existing scheduling, deadlock, process-monitor, and anomaly modules remain the source of truth; the Alert Engine normalizes and presents their reported results.

### Launch the Dashboard

```bash
python -m dashboard.main
```

## Setup

```bash
pip install -r requirements.txt
```

## Running Tests

```bash
python -m unittest discover -v
```

Or with pytest:

```bash
python -m pytest -v
```

## Tech Stack

| Tool        | Purpose                          |
|-------------|----------------------------------|
| Python 3.8+ | Core language                   |
| psutil      | Real-time system metrics         |
| Tkinter     | GUI framework                    |
| matplotlib  | Graphs, visualizations, Gantt charts |

## Notes

- This project is an educational monitoring and simulation system. It does not automatically kill or terminate processes, change process priority, throttle processes, or modify system resources.
- Alerts only report observations and suggest actions for human review.
- Both subsystems are designed with structured data (dicts/dataclasses) over print statements for programmatic dashboard consumption.
