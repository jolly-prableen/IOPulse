"""
demo_disk_scheduling.py – Phase 3 Demo: Disk Scheduling Algorithms
OS Sentinel – Teammate B (Memory & I/O Subsystem)

Run:  python demo_disk_scheduling.py
"""

import json

from disk_io.fcfs  import fcfs
from disk_io.sstf  import sstf
from disk_io.scan  import scan
from disk_io.cscan import cscan


def print_result(result):
    """Pretty-print a disk scheduling result."""
    algo = result["algorithm"]
    direction = result.get("direction", "")
    dir_label = f" ({direction})" if direction else ""

    print("=" * 62)
    print(f"  {algo}{dir_label} Disk Scheduling")
    print("=" * 62)
    print(f"  Initial Head Position : {result['initial_head']}")
    print(f"  Request Order         : {result['request_order']}")
    print(f"  Total Head Movement   : {result['total_head_movement']}")
    print(f"  Average Seek Distance : {result['average_seek_distance']}")
    print()
    print(f"  {'Step':>4}  {'From':>6}  {'To':>6}  {'Distance':>8}")
    print(f"  {'----':>4}  {'------':>6}  {'------':>6}  {'--------':>8}")
    for i, step in enumerate(result["steps"]):
        print(f"  {i+1:>4}  {step['from']:>6}  {step['to']:>6}  {step['distance']:>8}")
    print()
    print("=" * 62)
    print()


def main():
    requests   = [98, 183, 37, 122, 14, 124, 65, 67]
    head       = 53
    disk_size  = 200

    print()
    print("OS Sentinel – Phase 3: Disk Scheduling Algorithms Demo")
    print("(Teammate B – Memory & I/O Subsystem)")
    print()
    print(f"  Requests   : {requests}")
    print(f"  Head Start : {head}")
    print(f"  Disk Size  : {disk_size}")
    print()

    # Run all four algorithms
    result_fcfs  = fcfs(requests, head, disk_size)
    result_sstf  = sstf(requests, head, disk_size)
    result_scan  = scan(requests, head, disk_size, "right")
    result_cscan = cscan(requests, head, disk_size, "right")

    print_result(result_fcfs)
    print_result(result_sstf)
    print_result(result_scan)
    print_result(result_cscan)

    # Summary comparison
    print("=" * 62)
    print("  COMPARISON SUMMARY")
    print("=" * 62)
    print(f"  {'Algorithm':<16} {'Total Movement':>16} {'Avg Seek':>12}")
    print(f"  {'-'*16} {'-'*16} {'-'*12}")
    for r in [result_fcfs, result_sstf, result_scan, result_cscan]:
        label = r["algorithm"]
        if r.get("direction"):
            label += f" ({r['direction']})"
        print(f"  {label:<16} {r['total_head_movement']:>16} {r['average_seek_distance']:>12}")
    print("=" * 62)
    print()

    # Show raw JSON for one algorithm (dashboard-ready format)
    print("Raw structured output (FCFS) — dashboard-ready:")
    print(json.dumps(result_fcfs, indent=2))
    print()


if __name__ == "__main__":
    main()
