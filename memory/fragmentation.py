"""
memory/fragmentation.py – Memory Fragmentation Simulator
OS Sentinel – Teammate B (Memory & I/O Subsystem) – Phase 4A

=== OS CONCEPT: MEMORY FRAGMENTATION ===

When the OS allocates memory to processes, two kinds of wasted space
can appear:

1. **Internal Fragmentation**
   Memory is allocated in fixed-size blocks (e.g., 4 KB pages).  If a
   process requests 2.5 KB, it still gets a 4 KB block — the remaining
   1.5 KB inside the block is wasted.  This is *internal* fragmentation:
   wasted space *inside* allocated blocks.

2. **External Fragmentation**
   Over time, as processes are loaded and removed, free memory becomes
   scattered into many small, non-contiguous holes.  Even though the
   *total* free memory may be large enough for a new allocation, no
   single contiguous hole is big enough.  This is *external* fragmentation:
   wasted opportunity due to scattered free space.

=== DESIGN ===

This module provides two simulators:

  calculate_internal_fragmentation(allocations)
      Each allocation is a dict {"requested": int, "block_size": int}.
      Returns a structured result showing total wasted space.

  calculate_external_fragmentation(total_memory, blocks)
      `blocks` is a list of {"start": int, "size": int, "allocated": bool}.
      Returns a structured result showing free-space scatter.

Both return plain dictionaries ready for the dashboard.

=== STRUCTURED OUTPUT ===

Internal fragmentation result:
  {
      "type":                      "internal",
      "allocations":               [...],
      "total_requested":           int,
      "total_allocated":           int,
      "wasted_memory":             int,
      "fragmentation_percentage":  float,
  }

External fragmentation result:
  {
      "type":                      "external",
      "total_memory":              int,
      "allocated_memory":          int,
      "free_memory":               int,
      "num_free_blocks":           int,
      "free_blocks":               [...],
      "largest_free_block":        int,
      "external_fragmentation":    float,   # 0.0 – 1.0
      "fragmentation_percentage":  float,   # 0.0 – 100.0
  }
"""

from typing import Any, Dict, List


# ===================================================================
# Input validation helpers
# ===================================================================

def _validate_allocation(alloc: Dict[str, int], index: int) -> None:
    """Validate a single internal-fragmentation allocation entry.

    Each entry must have positive "requested" and "block_size", with
    block_size >= requested (you cannot allocate less than requested).

    Raises:
        ValueError – if the allocation is invalid.
    """
    if "requested" not in alloc or "block_size" not in alloc:
        raise ValueError(
            f"Allocation {index}: must have 'requested' and 'block_size' keys"
        )
    if alloc["requested"] <= 0:
        raise ValueError(
            f"Allocation {index}: 'requested' must be positive, "
            f"got {alloc['requested']}"
        )
    if alloc["block_size"] <= 0:
        raise ValueError(
            f"Allocation {index}: 'block_size' must be positive, "
            f"got {alloc['block_size']}"
        )
    if alloc["block_size"] < alloc["requested"]:
        raise ValueError(
            f"Allocation {index}: 'block_size' ({alloc['block_size']}) "
            f"cannot be smaller than 'requested' ({alloc['requested']})"
        )


def _validate_memory_block(block: Dict[str, Any], index: int) -> None:
    """Validate a single memory block entry for external fragmentation.

    Each block must have "start" >= 0, "size" > 0, and "allocated" (bool).

    Raises:
        ValueError – if the block is invalid.
    """
    for key in ("start", "size", "allocated"):
        if key not in block:
            raise ValueError(
                f"Block {index}: must have 'start', 'size', and "
                f"'allocated' keys"
            )
    if block["start"] < 0:
        raise ValueError(
            f"Block {index}: 'start' must be >= 0, got {block['start']}"
        )
    if block["size"] <= 0:
        raise ValueError(
            f"Block {index}: 'size' must be positive, got {block['size']}"
        )
    if not isinstance(block["allocated"], bool):
        raise ValueError(
            f"Block {index}: 'allocated' must be a bool, "
            f"got {type(block['allocated']).__name__}"
        )


# ===================================================================
# Internal Fragmentation
# ===================================================================

def calculate_internal_fragmentation(
    allocations: List[Dict[str, int]],
) -> Dict[str, Any]:
    """Calculate internal fragmentation from a list of memory allocations.

    === CONCEPT (simple explanation) ===
    Imagine you have boxes of fixed sizes (4 KB, 8 KB, etc.) and you need
    to pack items of various sizes into them.  If an item is 3 KB and the
    smallest available box is 4 KB, you waste 1 KB inside that box.  Sum up
    all such wasted space to get the total internal fragmentation.

    Parameters:
        allocations – List of dicts, each with:
            "requested":  int – bytes the process actually needs.
            "block_size": int – bytes actually allocated (>= requested).

    Returns:
        Structured result dict (see module docstring for format).

    Raises:
        ValueError – if any allocation entry is invalid.
    """
    for i, alloc in enumerate(allocations):
        _validate_allocation(alloc, i)

    # Handle empty allocation list.
    if not allocations:
        return {
            "type":                     "internal",
            "allocations":              [],
            "total_requested":          0,
            "total_allocated":          0,
            "wasted_memory":            0,
            "fragmentation_percentage": 0.0,
        }

    details: List[Dict[str, Any]] = []
    total_requested = 0
    total_allocated = 0

    for alloc in allocations:
        req  = alloc["requested"]
        blk  = alloc["block_size"]
        waste = blk - req

        total_requested += req
        total_allocated += blk

        details.append({
            "requested":  req,
            "block_size": blk,
            "wasted":     waste,
        })

    wasted = total_allocated - total_requested
    frag_pct = round((wasted / total_allocated) * 100, 2) if total_allocated > 0 else 0.0

    return {
        "type":                     "internal",
        "allocations":              details,
        "total_requested":          total_requested,
        "total_allocated":          total_allocated,
        "wasted_memory":            wasted,
        "fragmentation_percentage": frag_pct,
    }


# ===================================================================
# External Fragmentation
# ===================================================================

def calculate_external_fragmentation(
    total_memory: int,
    blocks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Calculate external fragmentation from a memory block layout.

    === CONCEPT (simple explanation) ===
    Imagine a parking lot with spaces numbered 0–999.  Some spaces are
    occupied (allocated blocks) and some are empty (free blocks).  Even
    if there are 300 empty spaces total, they might be scattered in small
    groups of 50, 100, 30, 70, 50.  If someone needs 200 contiguous
    spaces, they can't park — that's external fragmentation.

    External fragmentation ratio:
        1 - (largest_free_block / total_free_memory)

    When this ratio is 0, all free memory is in one contiguous block
    (no fragmentation).  When it approaches 1, free memory is highly
    scattered.

    Parameters:
        total_memory – Total size of the memory space.
        blocks       – List of dicts, each with:
            "start":     int  – starting address of the block.
            "size":      int  – size of the block.
            "allocated": bool – True if occupied, False if free.

    Returns:
        Structured result dict (see module docstring for format).

    Raises:
        ValueError – if inputs are invalid or blocks overlap/exceed memory.
    """
    if total_memory <= 0:
        raise ValueError(
            f"total_memory must be positive, got {total_memory}"
        )

    for i, block in enumerate(blocks):
        _validate_memory_block(block, i)

        # Ensure block doesn't exceed total memory.
        block_end = block["start"] + block["size"]
        if block_end > total_memory:
            raise ValueError(
                f"Block {i} (start={block['start']}, size={block['size']}) "
                f"exceeds total_memory ({total_memory})"
            )

    # Check for overlapping blocks.
    sorted_blocks = sorted(blocks, key=lambda b: b["start"])
    for i in range(1, len(sorted_blocks)):
        prev_end = sorted_blocks[i - 1]["start"] + sorted_blocks[i - 1]["size"]
        if sorted_blocks[i]["start"] < prev_end:
            raise ValueError(
                f"Blocks overlap: block ending at {prev_end} overlaps "
                f"with block starting at {sorted_blocks[i]['start']}"
            )

    # Handle empty block list (all memory is free).
    if not blocks:
        return {
            "type":                     "external",
            "total_memory":             total_memory,
            "allocated_memory":         0,
            "free_memory":              total_memory,
            "num_free_blocks":          1,
            "free_blocks":              [{"start": 0, "size": total_memory}],
            "largest_free_block":       total_memory,
            "external_fragmentation":   0.0,
            "fragmentation_percentage": 0.0,
        }

    # Separate allocated and explicitly-free blocks.
    allocated_memory = sum(b["size"] for b in blocks if b["allocated"])
    free_memory = total_memory - allocated_memory

    # Find free regions.  The free regions are:
    #   1. Gaps between blocks (including before the first and after the last).
    #   2. Explicitly free blocks listed in the input.
    # We compute free regions from the sorted block list by finding gaps.
    free_blocks: List[Dict[str, int]] = []

    # Check gap before the first block.
    if sorted_blocks[0]["start"] > 0:
        free_blocks.append({
            "start": 0,
            "size":  sorted_blocks[0]["start"],
        })

    # Check gaps between consecutive blocks.
    for i in range(1, len(sorted_blocks)):
        prev_end = sorted_blocks[i - 1]["start"] + sorted_blocks[i - 1]["size"]
        curr_start = sorted_blocks[i]["start"]
        if curr_start > prev_end:
            free_blocks.append({
                "start": prev_end,
                "size":  curr_start - prev_end,
            })

    # Check gap after the last block.
    last_end = sorted_blocks[-1]["start"] + sorted_blocks[-1]["size"]
    if last_end < total_memory:
        free_blocks.append({
            "start": last_end,
            "size":  total_memory - last_end,
        })

    # Add explicitly free blocks from the input.
    for b in blocks:
        if not b["allocated"]:
            # Check if this free block is already accounted for in gaps.
            already_found = any(
                fb["start"] == b["start"] and fb["size"] == b["size"]
                for fb in free_blocks
            )
            if not already_found:
                free_blocks.append({"start": b["start"], "size": b["size"]})

    # Sort free blocks by start address.
    free_blocks.sort(key=lambda fb: fb["start"])

    largest_free = max((fb["size"] for fb in free_blocks), default=0)

    # External fragmentation ratio:
    #   0 = all free memory is contiguous (ideal).
    #   1 = free memory is maximally scattered.
    if free_memory > 0:
        ext_frag = round(1 - (largest_free / free_memory), 4)
    else:
        ext_frag = 0.0

    frag_pct = round(ext_frag * 100, 2)

    return {
        "type":                     "external",
        "total_memory":             total_memory,
        "allocated_memory":         allocated_memory,
        "free_memory":              free_memory,
        "num_free_blocks":          len(free_blocks),
        "free_blocks":              free_blocks,
        "largest_free_block":       largest_free,
        "external_fragmentation":   ext_frag,
        "fragmentation_percentage": frag_pct,
    }
