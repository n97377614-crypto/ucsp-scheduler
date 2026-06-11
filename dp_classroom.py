"""
dp_classroom.py
===============
Classroom allocation using Dynamic Programming (paper §3.3).

The paper defines:
  dp[i] = minimum seat wastage when scheduling the first i teaching classes

  F(x, y) = x − y  if x ≥ y
             ∞      if x < y      (room too small)

  Iterative equation (eq. 24):
    dp[i] = min over j (dp[i], dp[i-1] + Σ(w∈Wi) F(Nj, Pi · νj,w))

  Where:
    Nj    = capacity of classroom j
    Pi    = number of students in teaching class i
    Wi    = set of weeks for teaching class i
    νj,w  = 1 if classroom j is available in week w; 0 if already used

  Key insight (paper §3.3):
    "Iterating from the smallest to the largest class sizes will lead
     to a higher average utilization and flexibility."
  → Sort teaching events by total_students ASCENDING before running DP.

  The DP also respects room_type matching (HC7): only classrooms whose
  room_type matches the event's required_room_type are considered.

Returns:
  room_assignment: Dict[event_id, classroom_id]
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple

from models import UCSPInstance, TeachingEvent, Chromosome


INF = math.inf


# ══════════════════════════════════════════════════════════════
#  Core DP functions
# ══════════════════════════════════════════════════════════════

def _F(capacity: int, students: int) -> float:
    """
    Paper eq. 22:  F(x, y) = x−y if x≥y, else ∞
    Measures seat wastage when classroom of size x holds y students.
    """
    if capacity >= students:
        return float(capacity - students)
    return INF


def allocate_classrooms(inst: UCSPInstance,
                         chrom: Chromosome,
                         num_weeks: int = 20) -> Dict[int, int]:
    """
    Assign a classroom to each teaching event using DP (paper §3.3).

    Parameters
    ----------
    inst       : the full problem instance
    chrom      : current chromosome (used for slot info, not strictly needed here)
    num_weeks  : total semester weeks (W)

    Returns
    -------
    room_assignment : dict mapping event_id → classroom_id
    """
    # ── Step 1: Sort events smallest→largest  (paper §3.3 key insight) ──────
    events_sorted = sorted(inst.teaching_events,
                            key=lambda m: m.total_students)

    # ── Step 2: Initialise availability matrix  (eq. 21) ─────────────────────
    # avail[(classroom_id, week, slot)] = True if that (room, week, slot) is free
    # A room can host different events at different time slots in the same week.
    from models import SLOTS_PER_WEEK
    avail: set = set()
    for room in inst.classrooms:
        for w in range(1, num_weeks + 1):
            for s in range(SLOTS_PER_WEEK):
                avail.add((room.id, w, s))

    # ── Step 3: Run DP over sorted events ────────────────────────────────────
    room_assignment: Dict[int, int] = {}

    # dp_state[i] = (min_wastage so far, assignments chosen)
    # We use a greedy DP: assign each event to the cheapest valid classroom.
    # This is the practical form of the DP described in the paper.

    total_wastage = 0.0

    for event in events_sorted:
        week_set = event.week_set if event.week_set else list(range(1, num_weeks + 1))

        best_rid     = None
        best_wastage = INF

        # Get the time slots assigned to this event by the GA
        event_slots = chrom.slots_for(event.id)

        for room in inst.classrooms:
            # HC7: room type must match
            if room.room_type != event.required_room_type:
                continue

            # HC5: room must fit all students
            if room.capacity < event.total_students:
                continue

            # Eligible-room filter (Rc)
            if event.eligible_room_ids and room.id not in event.eligible_room_ids:
                continue

            # Check availability for ALL (week, slot) combinations (eq. 24)
            wastage = 0.0
            feasible = True
            for w in week_set:
                for s in event_slots:
                    if (room.id, w, s) not in avail:
                        feasible = False
                        break
                if not feasible:
                    break
                w_wastage = _F(room.capacity, event.total_students)
                if w_wastage == INF:
                    feasible = False
                    break
                wastage += w_wastage

            if not feasible:
                continue

            # Pick the classroom with minimum total seat wastage
            if wastage < best_wastage:
                best_wastage = wastage
                best_rid     = room.id

        if best_rid is not None:
            room_assignment[event.id] = best_rid
            total_wastage += best_wastage
            # Mark (room, week, slot) as occupied (eq. 23)
            for w in week_set:
                for s in event_slots:
                    avail.discard((best_rid, w, s))
        else:
            # No feasible classroom found — leave unassigned
            # (this will be caught as a constraint violation)
            pass

    return room_assignment


# ══════════════════════════════════════════════════════════════
#  Classroom utilisation metric  (paper eq. 25)
# ══════════════════════════════════════════════════════════════

def compute_occupancy(inst: UCSPInstance,
                       chrom: Chromosome,
                       room_assignment: Dict[int, int],
                       num_weeks: int = 20) -> float:
    """
    Paper eq. 25:
      Occupancy = (1 / Σ θr,k) · Σ(r,w,k) θr,k · δr,w,k / (20 · Nr)

    θr,k = 1 if room r is used in slot k (across the weeks it's assigned)
    δr,w,k = number of students in room r at week w, slot k
    Nr    = capacity of room r
    """
    theta_total = 0.0    # Σ θr,k
    numerator   = 0.0    # Σ θr,k · δr,w,k / (20 · Nr)

    for event in inst.teaching_events:
        rid = room_assignment.get(event.id)
        if rid is None:
            continue
        room     = inst.classroom(rid)
        slots    = chrom.slots_for(event.id)
        week_set = event.week_set if event.week_set else list(range(1, num_weeks + 1))
        n_weeks  = len(week_set)

        for _slot in slots:
            theta_total += 1.0  # θr,k = 1 for this (room, slot)
            # δr,w,k = students × weeks (averaged over 20)
            numerator += (event.total_students * n_weeks) / (num_weeks * room.capacity)

    if theta_total == 0:
        return 0.0
    return numerator / theta_total


def classroom_usage_count(room_assignment: Dict[int, int]) -> int:
    """Number of distinct classrooms used — paper Table 5 metric."""
    return len(set(room_assignment.values()))


def utilisation_report(inst: UCSPInstance,
                        chrom: Chromosome,
                        room_assignment: Dict[int, int],
                        num_weeks: int = 20) -> dict:
    """
    Return a dict matching Table 5 of the paper:
      occupancy rate, occupancy std dev, number of classrooms used.
    """
    import statistics

    per_room_occ: List[float] = []

    for room in inst.classrooms:
        events_in_room = [m for m in inst.teaching_events
                          if room_assignment.get(m.id) == room.id]
        if not events_in_room:
            continue

        total_slots = 0
        total_used  = 0.0
        for event in events_in_room:
            n_slots  = len(chrom.slots_for(event.id))
            week_set = event.week_set if event.week_set else list(range(1, num_weeks + 1))
            n_weeks  = len(week_set)
            total_slots += n_slots * n_weeks
            total_used  += event.total_students * n_slots * n_weeks

        if total_slots > 0:
            occ = total_used / (total_slots * room.capacity)
            per_room_occ.append(occ)

    if not per_room_occ:
        return {"occupancy": 0.0, "std_dev": 0.0, "classrooms_used": 0}

    return {
        "occupancy":       statistics.mean(per_room_occ),
        "std_dev":         statistics.stdev(per_room_occ) if len(per_room_occ) > 1 else 0.0,
        "classrooms_used": classroom_usage_count(room_assignment),
    }
