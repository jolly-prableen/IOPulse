"""
memory/monitor.py – Live Memory Monitoring Module
OS Sentinel – Teammate B (Memory & I/O Subsystem)

=== OS CONCEPT ===
In any operating system, **memory management** is one of the core responsibilities
of the kernel. The OS must track:

  1. **Physical memory (RAM)**: How much total RAM is installed, how much is
     currently used by processes, and how much is available for new allocations.

  2. **Swap space**: When physical RAM runs out, the OS moves less-used pages
     to disk (swap). Heavy swap usage is a sign of memory pressure.

  3. **Per-process memory**: Each process has its own virtual address space.
     The OS tracks how much physical memory (RSS – Resident Set Size) each
     process actually occupies.  RSS is the portion of a process's memory
     that is held in RAM (as opposed to being swapped out or shared).

This module uses `psutil` to read these real metrics from the host OS, returning
structured data that can be consumed by the dashboard or anomaly detection
modules in later phases.

=== DESIGN ===
- All public functions return plain dictionaries so they are easy to serialize
  (JSON, SQLite) and easy to consume from Tkinter or matplotlib.
- Error handling wraps every per-process access because processes can terminate
  or become inaccessible (zombie, permission denied) between the time we list
  them and the time we read their details.
"""

import time
from typing import Any, Dict, List, Optional

import psutil


# ---------------------------------------------------------------------------
# Helper: human-readable byte formatting
# ---------------------------------------------------------------------------

def bytes_to_mb(byte_value: int) -> float:
    """Convert bytes to megabytes, rounded to 2 decimal places.

    We use MB because it is the most intuitive unit for memory sizes in the
    range that typical processes consume (a few MB to a few GB).
    """
    return round(byte_value / (1024 * 1024), 2)


# ---------------------------------------------------------------------------
# System-wide memory snapshot
# ---------------------------------------------------------------------------

def get_system_memory() -> Dict[str, Any]:
    """Capture a snapshot of system-wide RAM and swap usage.

    === OS CONCEPT ===
    The kernel exposes memory statistics through special files (e.g.,
    /proc/meminfo on Linux). `psutil` abstracts this across platforms so we
    get consistent data on Windows, Linux, and macOS.

    Returns a dictionary with:
        total_ram_mb      – Total physical RAM installed (MB)
        used_ram_mb       – RAM currently used by processes (MB)
        available_ram_mb  – RAM available for new processes (MB)
        ram_percent       – Percentage of RAM in use (0–100)
        total_swap_mb     – Total swap space configured (MB)
        used_swap_mb      – Swap space currently used (MB)
        swap_percent      – Percentage of swap in use (0–100)
        timestamp         – Unix timestamp of when the snapshot was taken
    """
    # psutil.virtual_memory() returns a named tuple with RAM stats.
    ram = psutil.virtual_memory()

    # psutil.swap_memory() returns a named tuple with swap/page-file stats.
    swap = psutil.swap_memory()

    return {
        "total_ram_mb":     bytes_to_mb(ram.total),
        "used_ram_mb":      bytes_to_mb(ram.used),
        "available_ram_mb": bytes_to_mb(ram.available),
        "ram_percent":      ram.percent,          # Already a float 0–100
        "total_swap_mb":    bytes_to_mb(swap.total),
        "used_swap_mb":     bytes_to_mb(swap.used),
        "swap_percent":     swap.percent,
        "timestamp":        time.time(),
    }


# ---------------------------------------------------------------------------
# Per-process memory information
# ---------------------------------------------------------------------------

def get_process_memory(top_n: int = 10) -> List[Dict[str, Any]]:
    """Return memory information for the top N processes by RAM usage.

    === OS CONCEPT ===
    Every process has a virtual address space managed by the OS.  The
    **Resident Set Size (RSS)** is the portion of that address space that is
    currently held in physical RAM.  Sorting by RSS tells us which processes
    are the biggest consumers of actual physical memory.

    Parameters:
        top_n  – Number of top processes to return (default 10).

    Returns a list of dictionaries, each containing:
        pid             – Process ID (unique identifier assigned by the OS)
        name            – Human-readable process name
        memory_percent  – Percentage of total RAM used by this process
        memory_rss_mb   – Resident Set Size in MB (None if unavailable)

    Processes that have terminated or are inaccessible are silently skipped.
    """
    processes: List[Dict[str, Any]] = []

    # psutil.process_iter() yields Process objects for every running process.
    # The attrs parameter pre-fetches the listed attributes efficiently.
    for proc in psutil.process_iter(attrs=["pid", "name", "memory_percent"]):
        try:
            info = proc.info  # Dict with the pre-fetched attributes

            # Fetch RSS separately via memory_info() because it is not
            # available through the fast-path attrs on all platforms.
            try:
                rss = proc.memory_info().rss    # bytes
                rss_mb = bytes_to_mb(rss)
            except (psutil.AccessDenied, psutil.ZombieProcess):
                # Some system processes restrict memory_info() access.
                rss_mb = None

            processes.append({
                "pid":            info["pid"],
                "name":           info["name"],
                "memory_percent": round(info["memory_percent"], 2) if info["memory_percent"] is not None else 0.0,
                "memory_rss_mb":  rss_mb,
            })

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # === OS CONCEPT ===
            # Processes can exit at any moment (race condition). A process
            # might be alive when process_iter() lists it but gone by the
            # time we read its details. This is normal and expected – we
            # simply skip it.
            continue

    # Sort descending by memory percentage so the heaviest consumers come first.
    processes.sort(key=lambda p: p["memory_percent"], reverse=True)

    return processes[:top_n]


# ---------------------------------------------------------------------------
# Combined snapshot (convenience function)
# ---------------------------------------------------------------------------

def get_memory_snapshot(top_n: int = 10) -> Dict[str, Any]:
    """Return a complete memory snapshot: system-wide stats + top processes.

    This is the main entry point that the dashboard and anomaly detection
    modules will call in future phases.

    Returns:
        {
            "system": { ... system memory dict ... },
            "processes": [ ... list of process dicts ... ]
        }
    """
    return {
        "system":    get_system_memory(),
        "processes": get_process_memory(top_n=top_n),
    }


# ---------------------------------------------------------------------------
# Pretty-print helper (for quick terminal demos, not for production use)
# ---------------------------------------------------------------------------

def print_snapshot(snapshot: Optional[Dict[str, Any]] = None) -> None:
    """Print a memory snapshot to the terminal in a readable format.

    If no snapshot is provided, a fresh one is taken automatically.
    This function is for development/demo purposes only – the dashboard
    will consume the raw dictionaries instead.
    """
    if snapshot is None:
        snapshot = get_memory_snapshot()

    sys_mem = snapshot["system"]

    print("=" * 60)
    print("  OS Sentinel – Live Memory Snapshot")
    print("=" * 60)
    print()
    print("  RAM")
    print(f"    Total:     {sys_mem['total_ram_mb']:>10.2f} MB")
    print(f"    Used:      {sys_mem['used_ram_mb']:>10.2f} MB")
    print(f"    Available: {sys_mem['available_ram_mb']:>10.2f} MB")
    print(f"    Usage:     {sys_mem['ram_percent']:>10.1f} %")
    print()
    print("  SWAP")
    print(f"    Total:     {sys_mem['total_swap_mb']:>10.2f} MB")
    print(f"    Used:      {sys_mem['used_swap_mb']:>10.2f} MB")
    print(f"    Usage:     {sys_mem['swap_percent']:>10.1f} %")
    print()
    print(f"  TOP {len(snapshot['processes'])} PROCESSES BY MEMORY")
    print(f"  {'PID':>7}  {'RSS (MB)':>10}  {'MEM %':>7}  NAME")
    print(f"  {'-'*7}  {'-'*10}  {'-'*7}  {'-'*20}")

    for proc in snapshot["processes"]:
        rss_str = f"{proc['memory_rss_mb']:.2f}" if proc["memory_rss_mb"] is not None else "N/A"
        print(f"  {proc['pid']:>7}  {rss_str:>10}  {proc['memory_percent']:>6.2f}%  {proc['name']}")

    print()
    print("=" * 60)
