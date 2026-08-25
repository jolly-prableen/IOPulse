# OS Sentinel

OS Sentinel is a modular operating-system learning project that implements explainable, rule-based process intelligence in phases.

## Phase 1: Real-Time Process Monitor

The monitor uses `psutil` to read live process information from the operating system and renders a simple terminal table showing:

- PID
- Name
- CPU%
- Memory%
- Priority
- Status

It refreshes every 1 second by default and safely skips processes that are inaccessible, missing, or zombie.

## Phase 2: FCFS Scheduling

The FCFS scheduler runs processes in arrival order and reports start time, completion time, turnaround time, and waiting time.

## Phase 3: SJF Scheduling

The SJF scheduler selects the available process with the shortest burst time and reports the same scheduling metrics.

## Phase 4: Priority Scheduling

The priority scheduler selects processes according to their priority while preserving deterministic scheduling metrics.

## Phase 5: Round Robin Scheduling

The Round Robin scheduler uses a configurable time quantum and returns execution order, completion, turnaround, and waiting metrics.

## Phase 6: Scheduling Metrics and Gantt Chart

The scheduling integration layer provides a common algorithm interface, calculates scheduling metrics, and generates a Gantt chart from the actual execution segments.

## Phase 7: Resource Allocation Graph

The Resource Allocation Graph models process requests and resource allocations. DFS-based cycle detection reports potential deadlocks without modifying system resources.

## Phase 8: Banker's Algorithm

The deadlock avoidance logic checks whether a resource-allocation state is safe by computing Need = Maximum - Allocation and then applying the standard Banker's Algorithm. It returns either a safe sequence or an unsafe warning. This logic is intentionally transparent and deterministic.

## Phase 9: Process Anomaly Detection

The anomaly detector is designed for explainable rule-based monitoring. It does not use machine learning. Instead, it applies simple, configurable heuristics to recent process observations and produces human-readable alerts.

### Runaway process detection

A runaway process warning is emitted when a process remains above a configurable CPU threshold, such as `90.0`, for a configured number of consecutive observations, such as `5`.

The detector includes:

- PID
- process name
- current CPU usage
- configured threshold
- consecutive observation count

It resets the counter whenever CPU usage falls below the threshold. A single brief spike does not trigger a runaway warning.

### Zombie process detection

When a process status is `zombie`, the detector emits a warning:

- `WARNING Zombie process detected.`
- Includes PID, process name, and status

### CPU starvation heuristic

The starvation heuristic is intentionally conservative and explainable. It does not claim that starvation is definitely happening. Instead, it looks for a process that remains active in recent observations and receives very low CPU time over a sustained period.

This is a heuristic based only on the data available from `psutil`:

- recent CPU observations
- recent timestamps
- process status
- CPU times collected from the process

The detector does not invent OS scheduler facts that cannot be observed directly.

### Configurable thresholds

Detection thresholds are intentionally easy to change in the implementation:

```python
CPU_THRESHOLD = 90.0
CONSECUTIVE_HIGH_CPU = 5
HISTORY_LIMIT = 100
```

These values are kept near the top of the anomaly module so they are simple to tune.

### Bounded process history

The detector stores only recent process observations using a fixed-size deque. This prevents unbounded growth and still allows short-term analysis for trend-based rules.

### Examples of alerts

```python
{
    "timestamp": "2024-01-01T00:00:00+00:00",
    "severity": "WARNING",
    "category": "runaway_process",
    "pid": 1234,
    "process_name": "python",
    "message": "WARNING Possible runaway process detected.",
    "observed_value": 96.2,
    "threshold": 90.0,
    "consecutive_observations": 5,
}
```

```python
{
    "timestamp": "2024-01-01T00:00:10+00:00",
    "severity": "WARNING",
    "category": "zombie_process",
    "pid": 3341,
    "process_name": "defunct",
    "message": "WARNING Zombie process detected.",
    "status": "zombie",
}
```

### Why rules instead of machine learning?

The detector is designed to be transparent and auditable. A simple rule-based design is easier to explain, easier to test, and easier to maintain in an educational OS monitoring project. The goal is clear reasoning, not hidden statistical inference.

## Run the monitor

```bash
python3 -m process_concurrency.process_monitor.process_monitor --refresh 1
```

You may stop it with `Ctrl+C`.

## Phase 10: OS Sentinel Desktop Dashboard

The dashboard is a Tkinter desktop window that integrates the existing process monitor, scheduling, deadlock, and anomaly modules without re-implementing their logic.

### Dashboard structure

The dashboard app is organized into a small set of GUI modules:

- [dashboard/main.py](dashboard/main.py): main application and tab management
- [dashboard/process_panel.py](dashboard/process_panel.py): live process monitor view
- [dashboard/scheduling_panel.py](dashboard/scheduling_panel.py): CPU scheduling simulation and Gantt chart handling
- [dashboard/deadlock_panel.py](dashboard/deadlock_panel.py): RAG and Banker's Algorithm interaction
- [dashboard/anomaly_panel.py](dashboard/anomaly_panel.py): anomaly detection display
- [dashboard/alert_engine.py](dashboard/alert_engine.py): bounded alert normalization and deduplication
- [dashboard/alert_panel.py](dashboard/alert_panel.py): recent alert display

### Dashboard tabs

The main window contains five tabs:

1. Process Monitor
   - displays live process information
   - refreshes automatically using Tkinter's `after()` method
   - reuses the existing monitor module

2. CPU Scheduling
   - accepts process arrival, burst, and priority inputs
   - runs FCFS, SJF, Priority, or Round Robin through the existing scheduling integration module
   - displays result tables and a Gantt chart

3. Deadlock
   - allows graph-based cycle detection via the existing Resource Allocation Graph module
   - checks safe state via the existing Banker's Algorithm

4. Anomaly Detection
   - shows warnings from the anomaly detector
   - uses the explainable process detection rules without external ML logic

5. Alerts
   - shows normalized anomaly and deadlock alerts
   - displays timestamp, severity, category, PID, message, and suggested action

### How the dashboard connects to existing modules

The final architecture is intentionally:

GUI
 ↓
Existing OS / Algorithm Modules
 ↓
Alert Engine where applicable
 ↓
OS / Scheduling / Deadlock / Detection logic

The GUI is a presentation layer. Existing scheduling, deadlock, process-monitor, and anomaly modules remain the source of truth; the Alert Engine only normalizes and presents their reported results.

### Launch the dashboard

From the project root:

```bash
cd "/Users/siddhi/Desktop/OS Sentinel"
python3 -m dashboard.main
```

### Run the complete test suite

```bash
cd "/Users/siddhi/Desktop/OS Sentinel"
python3 -m pytest -q
```

## Phase 11: Alert System

The Alert Engine in [dashboard/alert_engine.py](dashboard/alert_engine.py) provides a shared, bounded stream of explainable alerts for the dashboard. Each alert contains a timestamp, severity, category, message, optional PID, and suggested action.

Supported severity levels are `INFO`, `WARNING`, and `CRITICAL`. Existing anomaly detector output is normalized by the engine into runaway-process, zombie-process, and possible CPU-starvation alerts. Existing Resource Allocation Graph cycle results and Banker's Algorithm unsafe-state results are normalized into critical deadlock and unsafe-state alerts.

The engine keeps recent alerts in bounded history and suppresses identical category/PID/message alerts during a short duplicate window. The system is report-only: it never kills processes, changes priorities, throttles processes, or modifies system resources. Suggested actions require human investigation and explicit action outside the alert system.

The dashboard adds an Alerts tab showing timestamp, severity, category, PID, message, and suggested action. It refreshes through Tkinter's `after()` event-loop mechanism.

## Phase 12: Testing, Documentation & Cleanup

The final project includes focused tests for scheduling algorithms and metrics, Gantt-chart integration, process-monitor safety, deadlock analysis, anomaly rules, alert normalization and suppression, bounded histories, and dashboard tab construction. The complete suite is run with `python3 -m pytest -q`.

The project is an educational monitoring and simulation system. It does not automatically kill or terminate processes, change process priority, throttle processes, or modify system resources. Alerts only report observations and suggest actions for human review.

## Notes

This repository is complete through Phase 12. Phases 1 through 11 provide the process monitor, scheduling algorithms, deadlock analysis, anomaly detection, desktop dashboard, and alert system; Phase 12 records final testing, documentation, and cleanup.
