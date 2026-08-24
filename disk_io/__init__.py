"""
disk_io package – OS Sentinel (Teammate B)

This package handles disk scheduling simulation:
  - FCFS  (First Come First Serve)      – Phase 3
  - SSTF  (Shortest Seek Time First)    – Phase 3
  - SCAN  (Elevator Algorithm)          – Phase 3
  - C-SCAN (Circular SCAN)              – Phase 3

NOTE: This directory is named 'disk_io' (not 'io') to avoid shadowing
Python's built-in 'io' module.
"""

from disk_io.fcfs  import fcfs           # noqa: F401
from disk_io.sstf  import sstf           # noqa: F401
from disk_io.scan  import scan           # noqa: F401
from disk_io.cscan import cscan          # noqa: F401
