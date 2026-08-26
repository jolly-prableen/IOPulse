"""CPU scheduling algorithms for OS Sentinel."""

from .fcfs import fcfs_schedule, Process as FcfsProcess
from .integration import build_visualization, schedule_processes
from .priority import priority_schedule, Process as PriorityProcess
from .round_robin import round_robin_schedule, Process as RoundRobinProcess
from .sjf import sjf_schedule, Process as SjfProcess

__all__ = [
    "fcfs_schedule",
    "sjf_schedule",
    "priority_schedule",
    "round_robin_schedule",
    "schedule_processes",
    "build_visualization",
    "FcfsProcess",
    "SjfProcess",
    "PriorityProcess",
    "RoundRobinProcess",
]
