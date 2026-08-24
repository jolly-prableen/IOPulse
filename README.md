# OS Sentinel – Intelligent Process & Resource Management System
# Teammate B: Memory & I/O Subsystem

## Overview

OS Sentinel is a system monitoring and OS algorithm visualization tool.
This module (Teammate B) covers:

1. **Live Memory Monitoring** ← *Phase 1 (current)*
2. Paging & Page Replacement Simulation (FIFO, LRU, Optimal)
3. Memory Fragmentation (Internal & External)
4. Disk Scheduling Simulation (FCFS, SSTF, SCAN, C-SCAN)
5. Memory-side Anomaly Detection (Leak & Thrashing)
6. Memory/I/O Dashboard

## Project Structure

```
OS-Sentinel/
├── memory/            # Memory monitoring & simulation
│   ├── __init__.py
│   └── monitor.py     # Live RAM/swap/process monitoring
├── io/                # Disk scheduling (future)
│   └── __init__.py
├── intelligence/      # Anomaly detection (future)
│   └── __init__.py
├── dashboard/         # Tkinter + matplotlib GUI (future)
│   └── __init__.py
├── tests/             # Unit tests and demo scripts
│   └── test_monitor.py
├── main.py            # Entry point / demo runner
├── requirements.txt
└── README.md
```

## Phase 1: Live Memory Monitoring

### Setup

```bash
pip install -r requirements.txt
```

### Run the Monitor Demo

```bash
python main.py
```

This prints a snapshot of system memory (RAM, swap) and the top memory-consuming
processes, demonstrating that the monitoring foundation works.

### Run Tests

```bash
python -m pytest tests/ -v
```

Or without pytest:

```bash
python -m unittest tests.test_monitor -v
```

## Tech Stack

| Tool        | Purpose                          |
|-------------|----------------------------------|
| Python 3.8+ | Core language                   |
| psutil      | Real-time system metrics         |
| Tkinter     | GUI (future phases)              |
| matplotlib  | Graphs & visualizations (future) |

## Design Decisions

- **Structured data over print statements**: Every monitoring function returns
  dictionaries/dataclasses so the dashboard can consume data programmatically.
- **Independent module**: This subsystem has zero dependency on Teammate A's
  process/CPU code. Integration happens later through a shared interface.
- **Incremental development**: Each phase is built and tested before the next.
