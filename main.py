"""
main.py – OS Sentinel Entry Point
Teammate B: Memory & I/O Subsystem

Usage:
    python main.py          Launch the Tkinter GUI dashboard (Phase 5)
    python main.py --cli    Run the original terminal demo (Phase 1)
"""

import sys

from memory.monitor import get_memory_snapshot, print_snapshot


def run_cli_demo():
    """Run the original Phase 1 terminal demo."""
    print()
    print("OS Sentinel – Phase 1: Live Memory Monitoring Demo")
    print("(Teammate B – Memory & I/O Subsystem)")
    print()

    # Take a snapshot of system memory + top 10 processes.
    snapshot = get_memory_snapshot(top_n=10)

    # Pretty-print it to the terminal.
    print_snapshot(snapshot)

    # Also show the raw dictionary so we can verify the structure.
    print()
    print("Raw system data (this is what the dashboard will consume):")
    print(snapshot["system"])
    print()


def main():
    """Entry point — launch dashboard or CLI demo based on flags."""
    if "--cli" in sys.argv:
        run_cli_demo()
    else:
        # Import here to avoid pulling in Tkinter/matplotlib when
        # running in CLI mode or running tests.
        from dashboard.memory_io_dashboard import launch_dashboard
        launch_dashboard()


if __name__ == "__main__":
    main()
