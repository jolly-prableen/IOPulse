"""Deadlock detection utilities for IOPulse."""

from .bankers_algorithm import bankers_algorithm, run_bankers_algorithm
from .resource_allocation_graph import (
    ResourceAllocationGraph,
    add_process,
    add_resource,
    add_request_edge,
    add_allocation_edge,
    remove_edge,
    detect_cycle,
)

__all__ = [
    "ResourceAllocationGraph",
    "add_process",
    "add_resource",
    "add_request_edge",
    "add_allocation_edge",
    "remove_edge",
    "detect_cycle",
    "bankers_algorithm",
    "run_bankers_algorithm",
]
