"""Banker's Algorithm for safe-state detection in deadlock avoidance.

This implementation follows the standard textbook procedure:
- Need = Maximum - Allocation
- Work is initialized to Available
- Finish[i] = False for every process
- Find a process whose Need <= Work and Finish[i] is False
- Grant the request by updating Work += Allocation[i]
- Continue until either all processes finish or no such process exists

If all processes finish, the state is SAFE and a safe sequence is produced.
Otherwise, the state is UNSAFE.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


def _validate_matrix(name: str, matrix: Sequence[Sequence[Any]], expected_rows: int, expected_cols: int) -> List[List[int]]:
    """Validate a matrix and return it as a list of ints."""
    if matrix is None:
        raise ValueError(f"{name} matrix cannot be None.")

    normalized: List[List[int]] = []
    for row_index, row in enumerate(matrix):
        if row is None:
            raise ValueError(f"{name} row {row_index} cannot be None.")
        values = list(row)
        if len(values) != expected_cols:
            raise ValueError(f"{name} matrix row {row_index} must have {expected_cols} columns.")
        normalized_row: List[int] = []
        for col_index, value in enumerate(values):
            try:
                numeric_value = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} matrix has a non-integer value at row {row_index}, column {col_index}.") from exc
            if numeric_value < 0:
                raise ValueError(f"{name} matrix cannot contain negative values.")
            normalized_row.append(numeric_value)
        normalized.append(normalized_row)

    if len(normalized) != expected_rows:
        raise ValueError(f"{name} matrix must have {expected_rows} rows.")

    return normalized


def bankers_algorithm(
    available: Sequence[int],
    allocation: Sequence[Sequence[int]],
    maximum: Sequence[Sequence[int]],
) -> Dict[str, Any]:
    """Apply the Banker's Algorithm to test whether a state is safe.

    Args:
        available: available resources for each resource type
        allocation: matrix describing current allocations
        maximum: matrix describing maximum claims by each process

    Returns:
        {
            "safe": bool,
            "safe_sequence": [...],
            "available": [...],
            "allocation": [...],
            "maximum": [...],
            "need": [...],
            "message": "SAFE" or "UNSAFE"
        }
    """
    if available is None:
        raise ValueError("Available resources cannot be None.")

    available_list = list(available)
    if len(available_list) == 0:
        raise ValueError("Available resources must include at least one resource type.")
    if any(int(value) < 0 for value in available_list):
        raise ValueError("Available resources cannot contain negative values.")

    try:
        available_ints = [int(value) for value in available_list]
    except (TypeError, ValueError) as exc:
        raise ValueError("Available resources must be integers.") from exc

    if not allocation or not maximum:
        raise ValueError("Allocation and Maximum matrices cannot be empty.")

    process_count = len(allocation)
    resource_count = len(available_ints)

    if len(maximum) != process_count:
        raise ValueError("Allocation and Maximum must have the same number of rows (processes).")

    for row in allocation:
        if len(row) != resource_count:
            raise ValueError("Allocation row length must match the number of resource types.")

    for row in maximum:
        if len(row) != resource_count:
            raise ValueError("Maximum row length must match the number of resource types.")

    allocation_matrix = _validate_matrix("Allocation", allocation, process_count, resource_count)
    maximum_matrix = _validate_matrix("Maximum", maximum, process_count, resource_count)

    for process_index in range(process_count):
        for resource_index in range(resource_count):
            if allocation_matrix[process_index][resource_index] > maximum_matrix[process_index][resource_index]:
                raise ValueError(
                    "Allocation exceeds Maximum for process "
                    f"{process_index} and resource {resource_index}."
                )

    need_matrix = [
        [maximum_matrix[i][j] - allocation_matrix[i][j] for j in range(resource_count)]
        for i in range(process_count)
    ]

    work = available_ints[:]
    finish = [False for _ in range(process_count)]
    safe_sequence: List[str] = []

    while True:
        progress = False
        for process_index in range(process_count):
            if finish[process_index]:
                continue

            if all(need_matrix[process_index][resource_index] <= work[resource_index] for resource_index in range(resource_count)):
                work = [work[i] + allocation_matrix[process_index][i] for i in range(resource_count)]
                finish[process_index] = True
                safe_sequence.append(f"P{process_index}")
                progress = True

        if not progress:
            break

    if all(finish):
        return {
            "safe": True,
            "safe_sequence": safe_sequence,
            "available": available_ints,
            "allocation": allocation_matrix,
            "maximum": maximum_matrix,
            "need": need_matrix,
            "message": "SAFE",
        }

    return {
        "safe": False,
        "safe_sequence": [],
        "available": available_ints,
        "allocation": allocation_matrix,
        "maximum": maximum_matrix,
        "need": need_matrix,
        "message": "Unsafe State — No Safe Sequence Exists",
    }


def run_bankers_algorithm(
    available: Sequence[int],
    allocation: Sequence[Sequence[int]],
    maximum: Sequence[Sequence[int]],
) -> Dict[str, Any]:
    """Convenience wrapper for the Banker's Algorithm."""
    return bankers_algorithm(available, allocation, maximum)


if __name__ == "__main__":
    sample_available = [3, 3, 2]
    sample_allocation = [
        [0, 1, 0],
        [2, 0, 0],
        [3, 0, 2],
        [2, 1, 1],
    ]
    sample_maximum = [
        [7, 5, 3],
        [3, 2, 2],
        [9, 0, 2],
        [2, 2, 2],
    ]

    result = bankers_algorithm(sample_available, sample_allocation, sample_maximum)
    print(result["message"])
    print("Safe Sequence:", " → ".join(result["safe_sequence"]))
    print("Need:", result["need"])
