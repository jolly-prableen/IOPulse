"""Resource Allocation Graph (RAG) and cycle detection for deadlock analysis.

The graph supports two node types:
- process nodes
- resource nodes

It supports two directed edge types:
- process -> resource (request edge)
- resource -> process (allocation edge)

A cycle indicates a possible deadlock condition.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union


NodeType = str


@dataclass
class ResourceAllocationGraph:
    """A simple resource allocation graph for deadlock detection."""

    processes: Set[str] = field(default_factory=set)
    resources: Set[str] = field(default_factory=set)
    request_edges: Set[Tuple[str, str]] = field(default_factory=set)
    allocation_edges: Set[Tuple[str, str]] = field(default_factory=set)

    def add_process(self, process_id: str) -> None:
        """Add a process node to the graph."""
        self.processes.add(str(process_id))

    def add_resource(self, resource_id: str) -> None:
        """Add a resource node to the graph."""
        self.resources.add(str(resource_id))

    def add_request_edge(self, process_id: str, resource_id: str) -> None:
        """Add an edge of type: Process -> Resource."""
        self.add_process(process_id)
        self.add_resource(resource_id)
        self.request_edges.add((str(process_id), str(resource_id)))

    def add_allocation_edge(self, resource_id: str, process_id: str) -> None:
        """Add an edge of type: Resource -> Process."""
        self.add_resource(resource_id)
        self.add_process(process_id)
        self.allocation_edges.add((str(resource_id), str(process_id)))

    def remove_edge(self, source: str, target: str) -> None:
        """Remove a request or allocation edge if it exists."""
        self.request_edges.discard((source, target))
        self.allocation_edges.discard((source, target))

    def get_graph(self) -> Dict[str, List[str]]:
        """Return the graph as adjacency lists for easier debugging/testing."""
        adjacency: Dict[str, List[str]] = defaultdict(list)

        for source, target in self.request_edges:
            adjacency[source].append(target)
        for source, target in self.allocation_edges:
            adjacency[source].append(target)

        for node in self.processes | self.resources:
            adjacency.setdefault(node, [])

        for neighbors in adjacency.values():
            neighbors.sort()

        return dict(adjacency)

    def detect_cycle(self) -> Dict[str, Union[bool, List[str], str]]:
        """Detect whether a cycle exists and return the cycle path if found.

        This is implemented manually using DFS and track recursion stacks.
        """
        adjacency = self.get_graph()
        visited: Set[str] = set()
        in_stack: Set[str] = set()
        stack: List[str] = []

        def dfs(node: str) -> Optional[List[str]]:
            visited.add(node)
            in_stack.add(node)
            stack.append(node)

            for neighbor in adjacency.get(node, []):
                if neighbor not in visited:
                    cycle_path = dfs(neighbor)
                    if cycle_path is not None:
                        return cycle_path
                elif neighbor in in_stack:
                    start_index = stack.index(neighbor)
                    return stack[start_index:] + [neighbor]

            stack.pop()
            in_stack.remove(node)
            return None

        for node in sorted(adjacency):
            if node not in visited:
                cycle = dfs(node)
                if cycle is not None:
                    return {
                        "has_cycle": True,
                        "cycle": cycle,
                        "message": "Potential Deadlock Detected",
                    }

        return {
            "has_cycle": False,
            "cycle": [],
            "message": "No Deadlock Cycle Detected",
        }

    def __str__(self) -> str:
        """Provide a compact ASCII representation of the resource allocation graph."""
        lines: List[str] = []
        adjacency = self.get_graph()
        for node in sorted(adjacency):
            neighbors = adjacency[node]
            if neighbors:
                lines.append(f"{node} -> {', '.join(neighbors)}")
        return "\n".join(lines) if lines else "Graph is empty."


def add_process(graph: ResourceAllocationGraph, process_id: str) -> None:
    """Convenience helper for adding a process node."""
    graph.add_process(process_id)


def add_resource(graph: ResourceAllocationGraph, resource_id: str) -> None:
    """Convenience helper for adding a resource node."""
    graph.add_resource(resource_id)


def add_request_edge(graph: ResourceAllocationGraph, process_id: str, resource_id: str) -> None:
    """Convenience helper for adding a process -> resource edge."""
    graph.add_request_edge(process_id, resource_id)


def add_allocation_edge(graph: ResourceAllocationGraph, resource_id: str, process_id: str) -> None:
    """Convenience helper for adding a resource -> process edge."""
    graph.add_allocation_edge(resource_id, process_id)


def remove_edge(graph: ResourceAllocationGraph, source: str, target: str) -> None:
    """Convenience helper for removing an edge."""
    graph.remove_edge(source, target)


def detect_cycle(graph: ResourceAllocationGraph) -> Dict[str, Union[bool, List[str], str]]:
    """Convenience wrapper for cycle detection."""
    return graph.detect_cycle()
