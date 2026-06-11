"""
constraints.py
==============
Hard and soft constraint checking for the UCSP.

Hard constraints (HC1-HC9) from paper §2.4 (eqs 3-11).
Soft constraints (SC1-SC5) from paper §2.5 (eqs 12-18).

Also includes the 7-hard / 7-soft split from the grad project Chapter 3.

Every function takes a Chromosome and UCSPInstance and returns either:
  - int   (violation count, for hard constraints)
  - float (penalty score, for soft constraints)

Convention: lower is always better (we minimise).
"""

from __future__ import annotations
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from models import (
    Chromosome, UCSPInstance, TeachingEvent,
    DAYS_PER_WEEK, PERIODS_PER_DAY, SLOTS_PER_WEEK,
    slot_to_day_period,
)


# ══════════════════════════════════════════════════════════════
#  HARD CONSTRAINTS
# ══════════════════════════════════════════════════════════════

def hc1_teacher_conflict(chrom: Chromosome, inst: UCSPInstance) -> int:
    """
    HC1 / eq. 3:  Σ(c∈Ct) x[w,k,c] ≤ 1  ∀ w,k,t
    A teacher can teach at most one course per time slot.
    We work on the weekly template, so we ignore week index w here
    (same slot k = conflict regardless of week, unless week sets don't overlap).
    """
    violations = 0
    # teacher_id -> list of assigned slots (across all their events)
    teacher_slots: Dict[int, List[Tuple[int, List[int]]]] = defaultdict(list)

    for event in inst.teaching_events:
        slots = chrom.slots_for(event.id)
        if not slots:
            continue
        teacher_slots[event.teacher_id].append((event.id, slots, event.week_set))

    for tid, entries in teacher_slots.items():
        # For each pair of events sharing a teacher, check slot overlap
        for i in range(len(entries)):
            eid_a, slots_a, weeks_a = entries[i]
            for j in range(i + 1, len(entries)):
                eid_b, slots_b, weeks_b = entries[j]
                # Check if the two events share any week
                shared_weeks = set(weeks_a) & set(weeks_b)
                if not shared_weeks:
                    continue
                # Check if they share any slot
                if set(slots_a) & set(slots_b):
                    violations += 1

    return violations


def hc2_room_conflict(chrom: Chromosome, inst: UCSPInstance,
                       room_assignment: Dict[int, int]) -> int:
    """
    HC2 / eq. 4:  Σ(c∈Cr) x[w,k,c] ≤ 1  ∀ w,k,r
    A classroom can host at most one course per time slot.
    room_assignment: event_id -> classroom_id  (from DP phase)
    """
    violations = 0
    # (classroom_id, slot) -> list of event_ids
    room_slot_map: Dict[Tuple[int,int], List[int]] = defaultdict(list)

    for event in inst.teaching_events:
        rid = room_assignment.get(event.id)
        if rid is None:
            continue
        for slot in chrom.slots_for(event.id):
            room_slot_map[(rid, slot)].append(event.id)

    for (rid, slot), eids in room_slot_map.items():
        if len(eids) > 1:
            violations += len(eids) - 1

    return violations


def hc3_class_conflict(chrom: Chromosome, inst: UCSPInstance) -> int:
    """
    HC3 / eq. 5:  Σ(r∈R) L[w,k,r,e] ≤ 1  ∀ w,k,e
    An admin class can only be in one course at a time.
    """
    violations = 0
    # admin_class_id -> list of (slots, week_set)
    class_slot_map: Dict[int, List[Tuple[List[int], List[int]]]] = defaultdict(list)

    for event in inst.teaching_events:
        slots = chrom.slots_for(event.id)
        if not slots:
            continue
        for eid in event.admin_class_ids:
            class_slot_map[eid].append((slots, event.week_set))

    for eid, entries in class_slot_map.items():
        for i in range(len(entries)):
            slots_a, weeks_a = entries[i]
            for j in range(i + 1, len(entries)):
                slots_b, weeks_b = entries[j]
                if set(weeks_a) & set(weeks_b):
                    if set(slots_a) & set(slots_b):
                        violations += 1

    return violations


def hc4_required_hours(chrom: Chromosome, inst: UCSPInstance) -> int:
    """
    HC4 / eq. 6:  Σ(w,k) x[w,k,c] = Bc  ∀ c
    Each event must be assigned exactly weekly_hours slots.
    """
    violations = 0
    for event in inst.teaching_events:
        slots = chrom.slots_for(event.id)
        if len(slots) != event.weekly_hours:
            violations += abs(len(slots) - event.weekly_hours)
    return violations


def hc5_room_capacity(inst: UCSPInstance,
                       room_assignment: Dict[int, int]) -> int:
    """
    HC5 / eq. 7:  δ[r,w,k] ≤ Nr  ∀ r,w,k
    Room capacity must not be exceeded.
    room_assignment: event_id -> classroom_id
    """
    violations = 0
    for event in inst.teaching_events:
        rid = room_assignment.get(event.id)
        if rid is None:
            continue
        room = inst.classroom(rid)
        if event.total_students > room.capacity:
            violations += 1
    return violations


def hc6_joint_class_coordination(chrom: Chromosome,
                                   inst: UCSPInstance) -> int:
    """
    HC6 / eq. 8:  Σ(e∈Ep) L[w,k,r,e] = Sp  ∀ w,k,r
    For combined courses, ALL admin classes must meet at the SAME time.
    This is automatically satisfied by our encoding (one event covers
    all admin classes), but we verify no slot is missing.
    """
    violations = 0
    for event in inst.joint_events():
        slots = chrom.slots_for(event.id)
        if len(slots) != event.weekly_hours:
            violations += 1
    return violations


def hc7_room_type_match(inst: UCSPInstance,
                         room_assignment: Dict[int, int]) -> int:
    """
    HC7 / eq. 9:  ac = ar  ∀ c, r∈Rc
    Course type must match room type (e.g. lab course → lab room).
    """
    violations = 0
    for event in inst.teaching_events:
        rid = room_assignment.get(event.id)
        if rid is None:
            continue
        room = inst.classroom(rid)
        if event.required_room_type != room.room_type:
            violations += 1
    return violations


def hc8_fixed_slots(chrom: Chromosome, inst: UCSPInstance) -> int:
    """
    HC8 / eq. 10:  x[w,k,c] = 1  ∀ m∈M1, w∈Wm, k∈Km
    Fixed events must use their designated slots.
    """
    violations = 0
    for event in inst.teaching_events:
        if not event.is_fixed:
            continue
        actual = set(chrom.slots_for(event.id))
        required = set(event.fixed_slots)
        if actual != required:
            violations += 1
    return violations


def hc9_weekly_hours_completion(chrom: Chromosome,
                                  inst: UCSPInstance) -> int:
    """
    HC9 / eq. 11:  2 Σ(w,k) x[w,k,c] = Bc  ∀ c
    (Variant of HC4 used when courses span only part of the semester.)
    For our implementation, this duplicates HC4 since weekly_hours
    already encodes Bc. We count events where the slot count mismatches.
    """
    return hc4_required_hours(chrom, inst)


def count_hard_violations(chrom: Chromosome,
                            inst: UCSPInstance,
                            room_assignment: Dict[int, int] | None = None) -> int:
    """
    Total hard constraint violations across HC1-HC9.
    room_assignment may be None during the GA phase (before DP).
    """
    ra = room_assignment or {}
    total = 0
    total += hc1_teacher_conflict(chrom, inst)
    total += hc3_class_conflict(chrom, inst)
    total += hc4_required_hours(chrom, inst)
    total += hc6_joint_class_coordination(chrom, inst)
    total += hc8_fixed_slots(chrom, inst)
    if ra:
        total += hc2_room_conflict(chrom, inst, ra)
        total += hc5_room_capacity(inst, ra)
        total += hc7_room_type_match(inst, ra)
    return total


# ══════════════════════════════════════════════════════════════
#  SOFT CONSTRAINTS
# ══════════════════════════════════════════════════════════════

def sc1_course_even_distribution(chrom: Chromosome,
                                   inst: UCSPInstance) -> float:
    """
    SC1 / eq. 12:  min Σ(c∈C)(Σ(w,k) x[w,k,c] − Σ(w,d) σ[w,d,c])
    A course should be spread evenly across the week (not all on one day).
    Penalty = for each event: (slots used) - (distinct days used).
    Lower is better.
    """
    penalty = 0.0
    for event in inst.teaching_events:
        slots = chrom.slots_for(event.id)
        if not slots:
            penalty += event.weekly_hours
            continue
        days_used = len({slot_to_day_period(s)[0] for s in slots})
        # ideal: each slot on a different day
        penalty += len(slots) - days_used
    return penalty


def sc2_admin_class_day_balance(chrom: Chromosome,
                                  inst: UCSPInstance) -> float:
    """
    SC2 / eqs 13-14:  min (1/4) Σ(d)(Ye,d − Ȳe)²
    Courses for each admin class should be spread evenly across days.
    """
    penalty = 0.0
    for admin_class in inst.admin_classes:
        day_counts = [0] * DAYS_PER_WEEK   # Ye,d for d in D

        for event in inst.teaching_events:
            if admin_class.id not in event.admin_class_ids:
                continue
            for slot in chrom.slots_for(event.id):
                day, _ = slot_to_day_period(slot)
                day_counts[day] += 1

        total = sum(day_counts)
        if total == 0:
            continue
        mean = total / DAYS_PER_WEEK   # Ȳe
        variance = sum((y - mean) ** 2 for y in day_counts) / 4.0
        penalty += variance

    return penalty


def sc3_teacher_day_balance(chrom: Chromosome,
                              inst: UCSPInstance) -> float:
    """
    SC3 / eqs 15-16:  min (1/4) Σ(d)(Zt,d − Z̄t)²
    Each teacher's teaching load should be balanced across days.
    """
    penalty = 0.0
    for teacher in inst.teachers:
        day_counts = [0] * DAYS_PER_WEEK   # Zt,d

        for event in inst.teaching_events:
            if event.teacher_id != teacher.id:
                continue
            for slot in chrom.slots_for(event.id):
                day, _ = slot_to_day_period(slot)
                day_counts[day] += 1

        total = sum(day_counts)
        if total == 0:
            continue
        mean = total / DAYS_PER_WEEK   # Z̄t
        variance = sum((z - mean) ** 2 for z in day_counts) / 4.0
        penalty += variance

    return penalty


def sc4_teacher_preferences(chrom: Chromosome,
                              inst: UCSPInstance,
                              omega1: float = 1.0,
                              omega2: float = 0.0) -> float:
    """
    SC4 / eqs 1-2, 17:  min Σt(Qt − Vt)
    where Vt = ω1·Σ(θτ²) + ω2·Tmax

    Qt  = sum of preference scores for teacher t's assigned slots.
    Vt  = penalty for consecutive classes (ω1) and large gaps (ω2).

    Paper §4.1: ω1=1 (avoid consecutive classes), ω2=0 (ignore gaps)
    — this matches Chinese university preferences.

    We return Vt − Qt  so that minimising the fitness is consistent.
    (Higher Qt = better schedule, so we minimise Qt's negative.)
    """
    total_penalty = 0.0

    for teacher in inst.teachers:
        # Collect all slots this teacher teaches
        teacher_events = [m for m in inst.teaching_events
                          if m.teacher_id == teacher.id]

        # Qt: sum of preference scores
        Q_t = 0.0
        day_slots: Dict[int, List[int]] = defaultdict(list)

        for event in teacher_events:
            for slot in chrom.slots_for(event.id):
                Q_t += teacher.preference(slot)
                day, period = slot_to_day_period(slot)
                day_slots[day].append(period)

        # Vt: penalty for consecutive classes
        # θτ = 1 if τ > 1 (more than one consecutive session)
        V_t = 0.0
        for day, periods in day_slots.items():
            periods_sorted = sorted(set(periods))
            consecutive_run = 1
            for idx in range(1, len(periods_sorted)):
                if periods_sorted[idx] == periods_sorted[idx - 1] + 1:
                    consecutive_run += 1
                else:
                    if consecutive_run > 1:
                        # θτ = 1, penalty = τ²
                        V_t += omega1 * (consecutive_run ** 2)
                    consecutive_run = 1
            if consecutive_run > 1:
                V_t += omega1 * (consecutive_run ** 2)

            # ω2 term: maximum gap in the day
            if len(periods_sorted) > 1:
                max_gap = max(
                    periods_sorted[i+1] - periods_sorted[i] - 1
                    for i in range(len(periods_sorted) - 1)
                )
                V_t += omega2 * max_gap

        # F1 = Σt(Qt − Vt) → we want to MINIMISE (Vt − Qt)
        total_penalty += (V_t - Q_t)

    return total_penalty


def sc5_classroom_utilization(inst: UCSPInstance,
                               room_assignment: Dict[int, int]) -> float:
    """
    SC5 / eq. 18:  max (1 / Σθ) · Σ θr,k · δr,w,k / (20 · Nr)
    Maximise classroom utilisation; minimise the complement (1 − occupancy).

    occupancy = (Σ actual_students used) / (Σ capacity × weeks × slots used)
    """
    room_used_slots: Dict[int, int]   = defaultdict(int)   # rid -> #slots used
    room_used_seats: Dict[int, float] = defaultdict(float) # rid -> Σ students

    for event in inst.teaching_events:
        rid = room_assignment.get(event.id)
        if rid is None:
            continue
        num_weeks = len(event.week_set) if event.week_set else inst.num_weeks
        slots = chrom_slots_for_event(event.id)  # placeholder
        n_slots = len(slots)
        room_used_slots[rid] += n_slots * num_weeks
        room_used_seats[rid] += event.total_students * n_slots * num_weeks

    total_capacity_used = sum(
        inst.classroom(rid).capacity * n
        for rid, n in room_used_slots.items()
    )
    total_students_served = sum(room_used_seats.values())

    if total_capacity_used == 0:
        return 1.0  # worst case

    occupancy = total_students_served / total_capacity_used
    return 1.0 - occupancy   # minimise


def sc5_classroom_utilization_v2(inst: UCSPInstance,
                                   chrom: Chromosome,
                                   room_assignment: Dict[int, int]) -> float:
    """
    Correct version of SC5 using the chromosome's slot assignments.
    """
    room_used_slots:  Dict[int, int]   = defaultdict(int)
    room_used_seats:  Dict[int, float] = defaultdict(float)

    for event in inst.teaching_events:
        rid = room_assignment.get(event.id)
        if rid is None:
            continue
        slots = chrom.slots_for(event.id)
        n_slots    = len(slots)
        num_weeks  = len(event.week_set) if event.week_set else inst.num_weeks
        room_used_slots[rid]  += n_slots * num_weeks
        room_used_seats[rid]  += event.total_students * n_slots * num_weeks

    total_capacity = sum(
        inst.classroom(rid).capacity * n
        for rid, n in room_used_slots.items()
    )
    total_served = sum(room_used_seats.values())
    if total_capacity == 0:
        return 1.0
    return 1.0 - (total_served / total_capacity)


def compute_soft_penalties(chrom: Chromosome,
                            inst: UCSPInstance,
                            room_assignment: Dict[int, int] | None = None,
                            omega1: float = 1.0,
                            omega2: float = 0.0,
                            weights: Dict[str, float] | None = None) -> Dict[str, float]:
    """
    Compute all soft constraint penalties.
    Returns a dict {'sc1': ..., 'sc2': ..., 'sc3': ..., 'sc4': ..., 'sc5': ...}
    and 'total' = weighted sum.

    Default weights from grad project Chapter 3:
      w1=SC1=0.5, w2=SC2=1.0, w3=SC3=1.0, w4=SC4=1.0, w5=SC5=0.3
    """
    if weights is None:
        weights = {"sc1": 0.5, "sc2": 1.0, "sc3": 1.0, "sc4": 1.0, "sc5": 0.3}

    ra = room_assignment or {}

    sc = {
        "sc1": sc1_course_even_distribution(chrom, inst),
        "sc2": sc2_admin_class_day_balance(chrom, inst),
        "sc3": sc3_teacher_day_balance(chrom, inst),
        "sc4": sc4_teacher_preferences(chrom, inst, omega1, omega2),
        "sc5": sc5_classroom_utilization_v2(inst, chrom, ra) if ra else 0.0,
    }
    sc["total"] = sum(weights.get(k, 1.0) * v for k, v in sc.items() if k != "total")
    return sc
