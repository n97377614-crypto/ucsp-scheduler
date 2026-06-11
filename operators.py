"""
operators.py
============
Genetic operators for the UCSP GA.

Implements exactly the two novel operators from the paper:

  §3.2.2  Swap operation with the judgment mechanism
  ─────────────────────────────────────────────────
  Standard crossover picks a random course assignment and tries to swap
  its time slot between two parent solutions.  Before the swap is
  committed, a JUDGMENT CHECK verifies that:
    (a) All admin classes of the selected event are free in the new slot.
    (b) The assigned teacher is free in the new slot.
    (c) For joint events: none of the other admin-class events conflict.
  If the check fails, the swap is skipped (no invalid offspring generated).

  §3.2.3  Forced mutation with the repair mechanism
  ─────────────────────────────────────────────────
  Mutation randomly moves an event to a new slot.
  If this creates a constraint violation, the REPAIR MECHANISM:
    1. Identifies the conflicting event.
    2. Collects all valid (non-conflicting) slots.
    3. Randomly relocates the conflicting event to one of them.
    4. Repeats until all conflicts are resolved.

Paper parameters (§4.1):
  Pc = 0.8   (crossover probability)
  Pm = 0.01  (mutation probability)
"""

from __future__ import annotations
import random
from typing import Dict, List, Optional, Set, Tuple

from models import (
    Chromosome, UCSPInstance, TeachingEvent,
    SLOTS_PER_WEEK, slot_to_day_period,
)
from constraints import hc1_teacher_conflict, hc3_class_conflict


# ══════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════

def _teacher_occupied_slots(chrom: Chromosome,
                              inst: UCSPInstance,
                              teacher_id: int,
                              exclude_event_id: int = -1) -> Set[int]:
    """Return all slots occupied by teacher_id, excluding one event."""
    occupied: Set[int] = set()
    for event in inst.teaching_events:
        if event.teacher_id != teacher_id:
            continue
        if event.id == exclude_event_id:
            continue
        occupied.update(chrom.slots_for(event.id))
    return occupied


def _admin_class_occupied_slots(chrom: Chromosome,
                                  inst: UCSPInstance,
                                  admin_class_id: int,
                                  exclude_event_id: int = -1) -> Set[int]:
    """Return all slots occupied by admin_class_id, excluding one event."""
    occupied: Set[int] = set()
    for event in inst.teaching_events:
        if admin_class_id not in event.admin_class_ids:
            continue
        if event.id == exclude_event_id:
            continue
        occupied.update(chrom.slots_for(event.id))
    return occupied


def _is_slot_set_valid(candidate_slots: List[int],
                        event: TeachingEvent,
                        chrom: Chromosome,
                        inst: UCSPInstance) -> bool:
    """
    Judgment check: can event be placed at candidate_slots?
    Returns True only if:
      1. Candidate slots are distinct.
      2. Teacher is free in all candidate slots (when event is excluded).
      3. Every admin class of the event is free in all candidate slots.
    """
    if len(candidate_slots) != len(set(candidate_slots)):
        return False   # slots must be distinct

    teacher_busy = _teacher_occupied_slots(chrom, inst,
                                            event.teacher_id, event.id)
    for s in candidate_slots:
        if s in teacher_busy:
            return False   # teacher conflict

    for eid in event.admin_class_ids:
        busy = _admin_class_occupied_slots(chrom, inst, eid, event.id)
        for s in candidate_slots:
            if s in busy:
                return False   # class conflict

    return True


def _find_valid_slots(event: TeachingEvent,
                       chrom: Chromosome,
                       inst: UCSPInstance,
                       n_needed: int) -> Optional[List[int]]:
    """
    Repair helper: find n_needed non-conflicting slots for event.
    Returns a list of n_needed valid slot indices, or None if impossible.
    Slots are sampled randomly to avoid deterministic bias.
    """
    all_slots = list(range(SLOTS_PER_WEEK))
    random.shuffle(all_slots)

    teacher_busy = _teacher_occupied_slots(chrom, inst,
                                            event.teacher_id, event.id)
    class_busy: Set[int] = set()
    for eid in event.admin_class_ids:
        class_busy |= _admin_class_occupied_slots(chrom, inst, eid, event.id)

    forbidden = teacher_busy | class_busy

    # For fixed events, only their fixed slots are candidates
    if event.is_fixed:
        candidates = [s for s in event.fixed_slots if s not in forbidden]
    else:
        candidates = [s for s in all_slots if s not in forbidden]

    if len(candidates) < n_needed:
        return None

    return candidates[:n_needed]


# ══════════════════════════════════════════════════════════════
#  §3.2.2  Swap operation with judgment mechanism
# ══════════════════════════════════════════════════════════════

def crossover_with_judgment(parent_a: Chromosome,
                              parent_b: Chromosome,
                              inst: UCSPInstance,
                              crossover_prob: float = 0.8) -> Tuple[Chromosome, Chromosome]:
    """
    Single-point crossover adapted for UCSP with judgment check.

    For a randomly selected teaching event, we attempt to swap its
    slot assignment between parent_a and parent_b.

    The paper (§3.2.2, Figure 2) shows:
      – joint courses must be treated atomically (all admin classes move together)
      – swap is only committed if the judgment check passes for BOTH children

    Returns two offspring (possibly identical to parents if no valid swap found).
    """
    child_a = parent_a.copy()
    child_b = parent_b.copy()

    if random.random() > crossover_prob:
        return child_a, child_b

    if not inst.teaching_events:
        return child_a, child_b

    # Shuffle events and try each until a valid swap is found
    events = list(inst.teaching_events)
    random.shuffle(events)

    for event in events:
        slots_a = parent_a.slots_for(event.id)
        slots_b = parent_b.slots_for(event.id)

        # Skip if assignments are the same (no swap needed)
        if slots_a == slots_b:
            continue
        if not slots_a or not slots_b:
            continue

        # JUDGMENT CHECK for child_a  (gets slots_b for this event)
        child_a_temp = child_a.copy()
        child_a_temp.set_slots(event.id, slots_b)
        if not _is_slot_set_valid(slots_b, event, child_a_temp, inst):
            continue

        # JUDGMENT CHECK for child_b  (gets slots_a for this event)
        child_b_temp = child_b.copy()
        child_b_temp.set_slots(event.id, slots_a)
        if not _is_slot_set_valid(slots_a, event, child_b_temp, inst):
            continue

        # Both checks pass: commit the swap
        child_a.set_slots(event.id, slots_b)
        child_b.set_slots(event.id, slots_a)
        break   # one swap per crossover call (single-point)

    return child_a, child_b


# ══════════════════════════════════════════════════════════════
#  §3.2.3  Forced mutation with repair mechanism
# ══════════════════════════════════════════════════════════════

def mutate_with_repair(chrom: Chromosome,
                        inst: UCSPInstance,
                        mutation_prob: float = 0.01,
                        max_repair_attempts: int = 10) -> Chromosome:
    """
    For each event, with probability Pm, move it to a random new slot.

    If the move creates a violation, the REPAIR MECHANISM
    (paper §3.2.3, Figure 3):
      1. Detects the conflict.
      2. Finds valid alternative slots for the conflicting event.
      3. Relocates it randomly to one of those slots.
      4. Repeats up to max_repair_attempts times.

    The mutated chromosome is returned (in-place modification of a copy).
    """
    result = chrom.copy()

    for event in inst.teaching_events:
        if random.random() > mutation_prob:
            continue

        # Skip fixed events — they cannot be moved (HC8)
        if event.is_fixed:
            continue

        old_slots = result.slots_for(event.id)
        n_needed  = event.weekly_hours

        # Choose new random slots (different from current)
        all_slots = list(range(SLOTS_PER_WEEK))
        random.shuffle(all_slots)
        new_slots = [s for s in all_slots if s not in old_slots][:n_needed]

        if len(new_slots) < n_needed:
            continue  # can't find enough distinct new slots

        # Apply mutation
        result.set_slots(event.id, new_slots)

        # REPAIR MECHANISM: resolve any violations created
        _repair(result, inst, event.id, max_repair_attempts)

    return result


def _repair(chrom: Chromosome,
             inst: UCSPInstance,
             mutated_event_id: int,
             max_attempts: int) -> None:
    """
    Repair constraint violations introduced by a mutation.

    Strategy (paper §3.2.3):
      Find events that now conflict with the mutated event.
      Relocate each conflicting event to a random valid position.
      Repeat until no conflicts remain or max_attempts reached.
    """
    for attempt in range(max_attempts):
        conflicting = _find_conflicts(chrom, inst, mutated_event_id)
        if not conflicting:
            break   # fully repaired

        # Pick one conflicting event and relocate it
        victim_id = random.choice(conflicting)
        victim     = inst.event(victim_id)

        valid_slots = _find_valid_slots(victim, chrom, inst, victim.weekly_hours)
        if valid_slots is None:
            # Cannot repair this event — restore the mutated event's original
            # assignment is not possible here; we leave best-effort result
            break

        chrom.set_slots(victim_id, valid_slots)


def _find_conflicts(chrom: Chromosome,
                     inst: UCSPInstance,
                     reference_event_id: int) -> List[int]:
    """
    Return IDs of events that conflict with reference_event_id
    (teacher double-booking or admin-class double-booking).
    """
    ref_event  = inst.event(reference_event_id)
    ref_slots  = set(chrom.slots_for(reference_event_id))
    ref_teacher = ref_event.teacher_id
    ref_classes = set(ref_event.admin_class_ids)
    conflicts: List[int] = []

    for event in inst.teaching_events:
        if event.id == reference_event_id:
            continue
        other_slots = set(chrom.slots_for(event.id))
        if not other_slots & ref_slots:
            continue

        # Teacher conflict
        if event.teacher_id == ref_teacher:
            conflicts.append(event.id)
            continue

        # Admin-class conflict
        if set(event.admin_class_ids) & ref_classes:
            conflicts.append(event.id)

    return conflicts


# ══════════════════════════════════════════════════════════════
#  Tournament selection
# ══════════════════════════════════════════════════════════════

def tournament_select(population: List[Chromosome],
                       k: int = 3) -> Chromosome:
    """
    Paper §4: tournament selection.
    Pick k individuals at random; return the one with the lowest fitness.
    """
    contestants = random.sample(population, min(k, len(population)))
    return min(contestants, key=lambda c: c.fitness)


# ══════════════════════════════════════════════════════════════
#  Initial population  (random valid chromosomes)
# ══════════════════════════════════════════════════════════════

def random_chromosome(events: List[TeachingEvent],
                       inst: UCSPInstance) -> Chromosome:
    """
    Build one random chromosome by greedily assigning events to slots.

    For fixed events, their fixed slots are used directly.
    For other events, slots are chosen randomly from free positions
    (avoiding teacher and class conflicts as much as possible).

    This greedy initialisation mirrors the paper's approach of starting
    with diverse random populations.
    """
    chrom = Chromosome()

    # Process fixed events first  (HC8)
    for event in events:
        if event.is_fixed:
            chrom.set_slots(event.id, list(event.fixed_slots))

    # Then assign remaining events
    shuffled = [e for e in events if not e.is_fixed]
    random.shuffle(shuffled)

    for event in shuffled:
        valid = _find_valid_slots(event, chrom, inst, event.weekly_hours)
        if valid is not None:
            chrom.set_slots(event.id, valid)
        else:
            # Fallback: assign random slots even if conflicting
            # (fitness function will penalise; repair will fix later)
            slots = random.sample(range(SLOTS_PER_WEEK),
                                   min(event.weekly_hours, SLOTS_PER_WEEK))
            chrom.set_slots(event.id, slots)

    return chrom


def initialise_population(size: int,
                            events: List[TeachingEvent],
                            inst: UCSPInstance) -> List[Chromosome]:
    """Create an initial diverse population of `size` random chromosomes."""
    return [random_chromosome(events, inst) for _ in range(size)]
