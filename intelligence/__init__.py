"""
intelligence package – IOPulse

Modules:
  - memory_anomaly.py  – Memory leak & thrashing detection
  - io_metrics.py      – Process-level I/O telemetry collection & rate computation
  - io_classifier.py   – Process I/O behavior classification (CPU/IO/BALANCED/IDLE)
  - io_anomaly.py      – Process I/O anomaly detection (spike, stall, sustained high, ratio shift)
  - io_disk_bridge.py  – Bridge: process I/O telemetry → simulated disk scheduling analysis
"""
