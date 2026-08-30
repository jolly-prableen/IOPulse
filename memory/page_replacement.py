"""
memory/page_replacement.py – Page Replacement Algorithm Simulations
IOPulse – Memory & I/O Subsystem

=== OS CONCEPT: PAGING AND PAGE REPLACEMENT ===

When a process runs, the OS divides its memory into fixed-size blocks called
**pages**.  Physical RAM is divided into equally-sized blocks called **frames**.
The OS maps pages to frames using a **page table**.

Since RAM is limited, not all pages can be in memory at once.  When a process
accesses a page that is NOT currently in a frame, a **page fault** occurs:
the OS must load that page from disk into a frame.

If all frames are already occupied, the OS must choose a **victim page** to
evict.  The strategy for choosing the victim is called a **page replacement
algorithm**.  A good algorithm minimizes the total number of page faults.

This module implements three classic algorithms:

  1. FIFO  – Replace the page that has been in memory the longest.
  2. LRU   – Replace the page that has not been *used* for the longest time.
  3. Optimal – Replace the page that won't be needed for the longest time
               in the future (requires knowledge of future accesses; used
               as a theoretical benchmark).

=== DESIGN ===

Each algorithm function accepts:
  - pages:  A list of page numbers (the reference string).
  - frames: The number of physical frames available.

Each returns a dictionary:
  {
      "algorithm":   str,
      "page_faults": int,
      "page_hits":   int,
      "fault_rate":  float,   # 0.0 – 1.0
      "hit_rate":    float,   # 0.0 – 1.0
      "steps":       list     # one dict per page access
  }

Each step dict records the state after processing one page:
  {
      "page":   int,          # the page that was accessed
      "frames": list,         # current frame contents (None = empty slot)
      "hit":    bool,         # True if page was already in a frame
      "fault":  bool          # True if a page fault occurred
  }

This structured output makes it easy for the dashboard to animate the
algorithm step-by-step and for tests to verify correctness.
"""

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helper: build a result dictionary
# ---------------------------------------------------------------------------

def _build_result(
    algorithm: str,
    pages: List[int],
    steps: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble the final structured result from the list of steps.

    This is shared by all three algorithms so the output format is
    guaranteed to be consistent.
    """
    page_faults = sum(1 for s in steps if s["fault"])
    page_hits   = sum(1 for s in steps if s["hit"])
    total       = len(pages)

    return {
        "algorithm":   algorithm,
        "page_faults": page_faults,
        "page_hits":   page_hits,
        "fault_rate":  round(page_faults / total, 4) if total > 0 else 0.0,
        "hit_rate":    round(page_hits / total, 4)   if total > 0 else 0.0,
        "steps":       steps,
    }


# ===================================================================
# FIFO – First-In First-Out
# ===================================================================

def fifo(pages: List[int], num_frames: int) -> Dict[str, Any]:
    """Simulate the FIFO page replacement algorithm.

    === ALGORITHM (simple explanation) ===
    Think of the frames as a queue (like a line of people).  When a new
    page arrives and there's no room, we remove the page that has been
    waiting the LONGEST — the one at the front of the queue.

    Implementation:
      - We maintain a list `current_frames` of size `num_frames`.
      - A pointer `next_replace` tracks which frame to replace next
        (it cycles through 0, 1, 2, …, num_frames-1, 0, 1, …).
      - When a page fault occurs and all frames are full, we overwrite
        `current_frames[next_replace]` and advance the pointer.

    Parameters:
        pages      – The page reference string (e.g. [1, 2, 3, 1, 4]).
        num_frames – Number of physical frames available (e.g. 3).

    Returns:
        Structured result dict (see module docstring for format).
    """
    # Initialize frames to None (empty).
    current_frames: List[Optional[int]] = [None] * num_frames

    # FIFO pointer — tells us which frame to replace next.
    next_replace = 0

    steps: List[Dict[str, Any]] = []

    for page in pages:
        if page in current_frames:
            # --- PAGE HIT ---
            # The page is already loaded in a frame; no action needed.
            steps.append({
                "page":   page,
                "frames": list(current_frames),   # snapshot (copy)
                "hit":    True,
                "fault":  False,
            })
        else:
            # --- PAGE FAULT ---
            # The page is not in memory.  Load it into the next frame
            # indicated by the FIFO pointer.
            current_frames[next_replace] = page

            # Advance the pointer in a circular fashion.
            next_replace = (next_replace + 1) % num_frames

            steps.append({
                "page":   page,
                "frames": list(current_frames),   # snapshot (copy)
                "hit":    False,
                "fault":  True,
            })

    return _build_result("FIFO", pages, steps)


# ===================================================================
# LRU – Least Recently Used
# ===================================================================

def lru(pages: List[int], num_frames: int) -> Dict[str, Any]:
    """Simulate the LRU page replacement algorithm.

    === ALGORITHM (simple explanation) ===
    When we need to evict a page, we pick the one that hasn't been
    accessed for the longest time — the "Least Recently Used" page.

    Implementation:
      - We keep a list `current_frames` for the frame contents.
      - A parallel list `last_used` records the *step number* at which
        each frame was last accessed (loaded or hit).
      - On a page fault with full frames, we find the frame whose
        `last_used` value is the smallest (oldest access) and replace it.

    Parameters:
        pages      – The page reference string.
        num_frames – Number of physical frames available.

    Returns:
        Structured result dict.
    """
    current_frames: List[Optional[int]] = [None] * num_frames

    # last_used[i] = the step number when frame i was last accessed.
    # Initialized to -1 so empty frames are considered "oldest".
    last_used: List[int] = [-1] * num_frames

    steps: List[Dict[str, Any]] = []

    for step_index, page in enumerate(pages):
        if page in current_frames:
            # --- PAGE HIT ---
            # Update the last-used timestamp for this frame.
            frame_index = current_frames.index(page)
            last_used[frame_index] = step_index

            steps.append({
                "page":   page,
                "frames": list(current_frames),
                "hit":    True,
                "fault":  False,
            })
        else:
            # --- PAGE FAULT ---
            if None in current_frames:
                # There is still an empty frame — use it.
                victim = current_frames.index(None)
            else:
                # All frames are full.  Find the frame with the smallest
                # (oldest) last_used value — that's the LRU victim.
                victim = last_used.index(min(last_used))

            current_frames[victim] = page
            last_used[victim] = step_index

            steps.append({
                "page":   page,
                "frames": list(current_frames),
                "hit":    False,
                "fault":  True,
            })

    return _build_result("LRU", pages, steps)


# ===================================================================
# Optimal (Bélády's Algorithm)
# ===================================================================

def optimal(pages: List[int], num_frames: int) -> Dict[str, Any]:
    """Simulate the Optimal (Bélády's) page replacement algorithm.

    === ALGORITHM (simple explanation) ===
    When we need to evict a page, we look AHEAD in the reference string
    and evict the page whose next use is farthest in the future.  If a
    page is never used again, it is the best candidate for eviction.

    This algorithm is **not implementable in a real OS** because it
    requires knowledge of future page accesses.  It serves as a
    **theoretical lower bound** — no other algorithm can produce fewer
    page faults than Optimal on the same reference string.

    Implementation:
      - For each page fault (when frames are full), we scan forward in
        the reference string from the current position.
      - For each page currently in a frame, we find its next occurrence.
      - We evict the page whose next occurrence is the farthest away, or
        one that never appears again.

    Parameters:
        pages      – The page reference string.
        num_frames – Number of physical frames available.

    Returns:
        Structured result dict.
    """
    current_frames: List[Optional[int]] = [None] * num_frames

    steps: List[Dict[str, Any]] = []

    for step_index, page in enumerate(pages):
        if page in current_frames:
            # --- PAGE HIT ---
            steps.append({
                "page":   page,
                "frames": list(current_frames),
                "hit":    True,
                "fault":  False,
            })
        else:
            # --- PAGE FAULT ---
            if None in current_frames:
                # There is still an empty frame — use it.
                victim = current_frames.index(None)
            else:
                # All frames are full.  Find the page whose next use is
                # farthest in the future.
                victim = _find_optimal_victim(
                    current_frames, pages, step_index
                )

            current_frames[victim] = page

            steps.append({
                "page":   page,
                "frames": list(current_frames),
                "hit":    False,
                "fault":  True,
            })

    return _build_result("Optimal", pages, steps)


def _find_optimal_victim(
    current_frames: List[Optional[int]],
    pages: List[int],
    current_index: int,
) -> int:
    """Find the frame index of the page to evict using the Optimal strategy.

    For each page currently in a frame, we look ahead in the reference
    string (starting after `current_index`) to find when it will next
    be used.  The page with the farthest (or no) future use is chosen.

    Returns:
        The index within `current_frames` of the victim page.
    """
    farthest_use  = -1    # The farthest next-use distance seen so far.
    victim_index  = 0     # Frame index of the best victim so far.

    # The future portion of the reference string (after the current page).
    future = pages[current_index + 1:]

    for frame_idx, frame_page in enumerate(current_frames):
        if frame_page is None:
            # Should not happen here (caller checks), but be safe.
            continue

        try:
            # Find the next occurrence of this page in the future.
            next_use = future.index(frame_page)
        except ValueError:
            # This page is NEVER used again — it's the ideal victim.
            return frame_idx

        if next_use > farthest_use:
            farthest_use = next_use
            victim_index = frame_idx

    return victim_index


# ---------------------------------------------------------------------------
# Convenience: run all three algorithms on the same input
# ---------------------------------------------------------------------------

def compare_algorithms(
    pages: List[int], num_frames: int
) -> Dict[str, Dict[str, Any]]:
    """Run FIFO, LRU, and Optimal on the same input and return all results.

    This is useful for the dashboard to display a side-by-side comparison.

    Returns:
        {
            "FIFO":    { ... result dict ... },
            "LRU":     { ... result dict ... },
            "Optimal": { ... result dict ... },
        }
    """
    return {
        "FIFO":    fifo(pages, num_frames),
        "LRU":     lru(pages, num_frames),
        "Optimal": optimal(pages, num_frames),
    }


# ---------------------------------------------------------------------------
# Pretty-print helper (for quick terminal demos)
# ---------------------------------------------------------------------------

def print_result(result: Dict[str, Any]) -> None:
    """Print a page replacement result to the terminal in a readable format.

    This is for development/demo purposes.  The dashboard will consume
    the raw dictionaries directly.
    """
    print("=" * 60)
    print(f"  {result['algorithm']} Page Replacement")
    print("=" * 60)
    print()

    num_frames = len(result["steps"][0]["frames"]) if result["steps"] else 0

    # Header
    header = f"  {'Step':>4}  {'Page':>4}  "
    header += "  ".join(f"F{i}" for i in range(num_frames))
    header += f"  {'Result':>8}"
    print(header)
    print(f"  {'-'*4}  {'-'*4}  " + "  ".join("--" for _ in range(num_frames)) + f"  {'-'*8}")

    for i, step in enumerate(result["steps"]):
        row = f"  {i+1:>4}  {step['page']:>4}  "
        for frame_val in step["frames"]:
            row += f"{str(frame_val) if frame_val is not None else '--':>2}  "
        row += "HIT" if step["hit"] else "FAULT"
        print(row)

    print()
    print(f"  Page Faults: {result['page_faults']}")
    print(f"  Page Hits:   {result['page_hits']}")
    print(f"  Fault Rate:  {result['fault_rate']:.2%}")
    print(f"  Hit Rate:    {result['hit_rate']:.2%}")
    print("=" * 60)
    print()
