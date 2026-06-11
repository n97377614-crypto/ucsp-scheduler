"""
scheduler.py
============
The POGA-DP orchestrator (paper §3 "Optimizing the UCSP Using POGA-DP").

Two-phase algorithm (paper §3.1):

  Phase 1 – Joint course time-slot scheduling
  ────────────────────────────────────────────
  "A genetic algorithm was initially used to schedule the class times
   for combined scheduling tasks. After obtaining a solution with a
   sufficient fit, the genetic algorithm was then applied to scheduling
   the time slots for independent scheduling tasks."

  → Run GA on JOINT events only first.
    Joint courses are harder (they constrain multiple admin classes
    simultaneously), so solving them first leaves the easiest slots
    free for independent courses.

  Phase 2 – Independent course time-slot scheduling
  ──────────────────────────────────────────────────
  → Run GA on INDEPENDENT events, fixing the Phase 1 assignments.
    Independent events only affect one admin class at a time.

  Phase 3 – Classroom allocation (DP)
  ─────────────────────────────────────
  "A combination of greedy algorithms and dynamic programming was
   employed to allocate classroom locations for the courses."
  → Run DP on the merged chromosome from phases 1+2.

References
----------
Grad project Chapter 4 §4.3-§4.4
Paper §3.1-§3.3
"""

from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from models import (
    Chromosome, UCSPInstance, TeachingEvent, ScheduledEvent,
    SLOTS_PER_WEEK, DAY_NAMES, PERIOD_NAMES, slot_to_day_period,
)
from ga_engine import GAConfig, GAResult, run_ga
from dp_classroom import allocate_classrooms, utilisation_report, compute_occupancy
from fitness import evaluate, is_feasible, fitness_breakdown


# ──────────────────────────────────────────────────────────────
# Result container
# ──────────────────────────────────────────────────────────────

@dataclass
class SchedulingResult:
    """
    Complete output of one POGA-DP run, ready for the API / frontend.
    """
    chromosome:      Chromosome
    room_assignment: Dict[int, int]           # event_id → classroom_id
    scheduled_events: List[ScheduledEvent]

    # Per-phase GA results
    phase1_result: Optional[GAResult] = None
    phase2_result: Optional[GAResult] = None

    # Quality metrics
    final_fitness:     float = 0.0
    hard_violations:   int   = 0
    feasible:          bool  = False
    occupancy:         float = 0.0
    classrooms_used:   int   = 0
    fitness_breakdown: dict  = field(default_factory=dict)
    utilisation_report: dict = field(default_factory=dict)

    def summary(self) -> str:
        status = "✓ FEASIBLE" if self.feasible else "✗ INFEASIBLE"
        return (
            f"{status} | fitness={self.final_fitness:.2f} | "
            f"violations={self.hard_violations} | "
            f"rooms={self.classrooms_used} | "
            f"occupancy={self.occupancy*100:.1f}%"
        )


# ──────────────────────────────────────────────────────────────
# POGA-DP  main entry point
# ──────────────────────────────────────────────────────────────

def run_poga_dp(inst: UCSPInstance,
                config: GAConfig,
                progress_callback: Optional[Callable[[str, int, float], None]] = None
               ) -> SchedulingResult:
    """
    Run the full POGA-DP algorithm on a problem instance.

    Parameters
    ----------
    inst             : the full UCSP instance (courses, teachers, rooms…)
    config           : GA hyper-parameters
    progress_callback: optional f(phase_name, generation, best_fitness)
                       used by the API to stream progress to the client.

    Returns
    -------
    SchedulingResult with the complete schedule and all quality metrics.
    """
    inst.build_indices()

    joint_events       = inst.joint_events()
    independent_events = inst.independent_events()

    print(f"\n{'='*60}")
    print(f"POGA-DP | {inst.summary()}")
    print(f"{'='*60}")
    print(f"Phase 1: {len(joint_events)} joint events")
    print(f"Phase 2: {len(independent_events)} independent events")

    # ────────────────────────────────────────────────────────
    # PHASE 1 – Schedule joint (combined) courses
    # ────────────────────────────────────────────────────────
    phase1_result: Optional[GAResult] = None
    merged_chromosome = Chromosome()

    if joint_events:
        print("\n[Phase 1] Running GA on joint courses...")

        def cb1(gen, fit):
            if progress_callback:
                progress_callback("phase1", gen, fit)
            if gen % 100 == 0:
                print(f"  gen={gen:4d}  best_fitness={fit:.2f}")

        phase1_result = run_ga(
            events=joint_events,
            inst=inst,
            config=config,
            progress_callback=cb1,
        )
        print(f"  {phase1_result.summary()}")

        # Merge phase 1 assignments into the combined chromosome
        for eid, slots in phase1_result.best_chromosome.assignment.items():
            merged_chromosome.set_slots(eid, slots)
    else:
        print("[Phase 1] No joint events — skipping.")

    # ────────────────────────────────────────────────────────
    # PHASE 2 – Schedule independent courses
    # Locked assignments from Phase 1 are treated as "fixed" context.
    # ────────────────────────────────────────────────────────
    phase2_result: Optional[GAResult] = None

    if independent_events:
        print("\n[Phase 2] Running GA on independent courses...")

        # Inject Phase 1 assignments so HC1/HC3 checking is aware of them
        # by using a combined "context" chromosome passed into the operators.
        # We achieve this by creating "phantom fixed events" in the context
        # OR simply by evaluating with the merged chromosome.
        # The cleanest approach: run GA with a partial chromosome pre-filled.

        partial_chrom = merged_chromosome.copy()

        def cb2(gen, fit):
            if progress_callback:
                progress_callback("phase2", gen, fit)
            if gen % 100 == 0:
                print(f"  gen={gen:4d}  best_fitness={fit:.2f}")

        phase2_result = _run_ga_with_context(
            events=independent_events,
            inst=inst,
            config=config,
            context_chromosome=partial_chrom,
            progress_callback=cb2,
        )
        print(f"  {phase2_result.summary()}")

        # Merge phase 2 into combined chromosome
        for eid, slots in phase2_result.best_chromosome.assignment.items():
            merged_chromosome.set_slots(eid, slots)
    else:
        print("[Phase 2] No independent events — skipping.")

    # ────────────────────────────────────────────────────────
    # PHASE 3 – Classroom allocation (DP)
    # ────────────────────────────────────────────────────────
    print("\n[Phase 3] DP classroom allocation...")
    room_assignment = allocate_classrooms(inst, merged_chromosome, inst.num_weeks)
    print(f"  Classrooms used: {len(set(room_assignment.values()))}")

    # ────────────────────────────────────────────────────────
    # Final evaluation
    # ────────────────────────────────────────────────────────
    evaluate(merged_chromosome, inst, room_assignment, config.sc_weights)
    breakdown = fitness_breakdown(merged_chromosome, inst, room_assignment)
    util      = utilisation_report(inst, merged_chromosome, room_assignment, inst.num_weeks)
    occupancy = compute_occupancy(inst, merged_chromosome, room_assignment, inst.num_weeks)

    # ────────────────────────────────────────────────────────
    # Build output objects
    # ────────────────────────────────────────────────────────
    scheduled = _build_scheduled_events(merged_chromosome, inst, room_assignment)

    result = SchedulingResult(
        chromosome=merged_chromosome,
        room_assignment=room_assignment,
        scheduled_events=scheduled,
        phase1_result=phase1_result,
        phase2_result=phase2_result,
        final_fitness=merged_chromosome.fitness,
        hard_violations=breakdown["hard_total"],
        feasible=breakdown["feasible"],
        occupancy=occupancy,
        classrooms_used=util["classrooms_used"],
        fitness_breakdown=breakdown,
        utilisation_report=util,
    )

    print(f"\n{'='*60}")
    print(f"RESULT: {result.summary()}")
    print(f"{'='*60}\n")

    return result


# ──────────────────────────────────────────────────────────────
# Helper: run GA while respecting context assignments
# ──────────────────────────────────────────────────────────────

def _run_ga_with_context(events: List[TeachingEvent],
                          inst: UCSPInstance,
                          config: GAConfig,
                          context_chromosome: Chromosome,
                          progress_callback) -> GAResult:
    """
    Run the GA for a subset of events, keeping Phase-1 slot assignments
    visible to the constraint checker.

    We create a "shadow instance" where the context events appear as
    fixed events inside the chromosome, so HC1/HC3 are checked globally.

    Implementation: the fitness function always uses the merged chromosome
    (context + current assignments), so slot conflicts with Phase 1 events
    are detected naturally.
    """
    from operators import initialise_population, tournament_select
    from operators import crossover_with_judgment, mutate_with_repair
    from fitness import evaluate, is_feasible
    import time

    start_time = time.time()
    fitness_history = []
    avg_history     = []

    # Create initial population for the INDEPENDENT events only,
    # using the context (phase-1 slots) to avoid double-booking.
    population = []
    for _ in range(config.population_size):
        indep_chrom = context_chromosome.copy()
        # Fill in independent events with random valid slots
        from operators import random_chromosome
        rand = random_chromosome(events, inst)
        # We need to merge rand into indep_chrom but check against context
        for ev in events:
            slots = rand.slots_for(ev.id)
            indep_chrom.set_slots(ev.id, slots)
        population.append(indep_chrom)

    # Evaluate
    for chrom in population:
        evaluate(chrom, inst, None, config.sc_weights, config.omega1, config.omega2)
    population.sort(key=lambda c: c.fitness)
    best = population[0].copy()

    fitness_history.append(best.fitness)
    avg_history.append(sum(c.fitness for c in population) / len(population))

    for gen in range(1, config.max_generations + 1):
        phase_ratio = gen / config.max_generations
        if phase_ratio < config.explore_phase_ratio:
            pm = config.mutation_prob * config.explore_mutation_mult
            tk = max(2, config.tournament_k - 1)
        elif phase_ratio > config.refine_phase_ratio:
            pm = config.mutation_prob * config.refine_mutation_mult
            tk = config.tournament_k + 1
        else:
            pm = config.mutation_prob
            tk = config.tournament_k

        next_pop = []
        if config.elitism:
            next_pop.append(best.copy())

        while len(next_pop) < config.population_size:
            pa = tournament_select(population, k=tk)
            pb = tournament_select(population, k=tk)
            ca, cb = crossover_with_judgment(pa, pb, inst, config.crossover_prob)
            ca = mutate_with_repair(ca, inst, pm, config.max_repair_attempts)
            cb = mutate_with_repair(cb, inst, pm, config.max_repair_attempts)
            next_pop.append(ca)
            if len(next_pop) < config.population_size:
                next_pop.append(cb)

        population = next_pop
        for chrom in population:
            evaluate(chrom, inst, None, config.sc_weights, config.omega1, config.omega2)
        population.sort(key=lambda c: c.fitness)

        if population[0].fitness < best.fitness:
            best = population[0].copy()

        fitness_history.append(best.fitness)
        avg_history.append(sum(c.fitness for c in population) / len(population))

        if progress_callback:
            progress_callback(gen, best.fitness)

        if config.time_limit_sec > 0:
            if time.time() - start_time >= config.time_limit_sec:
                break

        if best.fitness < 1.0:
            break

    elapsed = time.time() - start_time
    from ga_engine import GAResult
    return GAResult(
        best_chromosome=best,
        best_fitness=best.fitness,
        fitness_history=fitness_history,
        avg_history=avg_history,
        generations_run=len(fitness_history),
        elapsed_sec=elapsed,
        feasible=is_feasible(best, inst),
    )


# ──────────────────────────────────────────────────────────────
# Build final ScheduledEvent list
# ──────────────────────────────────────────────────────────────

def _build_scheduled_events(chrom: Chromosome,
                              inst: UCSPInstance,
                              room_assignment: Dict[int, int]
                             ) -> List[ScheduledEvent]:
    events = []
    for ev in inst.teaching_events:
        slots = chrom.slots_for(ev.id)
        rid   = room_assignment.get(ev.id)
        events.append(ScheduledEvent(
            event_id=ev.id,
            course_id=ev.course_id,
            teacher_id=ev.teacher_id,
            admin_class_ids=ev.admin_class_ids,
            timeslots=slots,
            week_set=ev.week_set if ev.week_set else list(range(1, inst.num_weeks + 1)),
            classroom_id=rid,
        ))
    return events


# ──────────────────────────────────────────────────────────────
# Timetable grid view (text)
# ──────────────────────────────────────────────────────────────

def format_timetable(result: SchedulingResult,
                      inst: UCSPInstance,
                      admin_class_id: int | None = None) -> str:
    """
    Return an ASCII timetable grid for one admin class (or all if None).
    Rows = periods (P1-P5), Columns = days (Mon-Fri).
    """
    from models import DAYS_PER_WEEK, PERIODS_PER_DAY

    # grid[period][day] = text label
    grid = [["-" * 12 for _ in range(DAYS_PER_WEEK)] for _ in range(PERIODS_PER_DAY)]

    for se in result.scheduled_events:
        if admin_class_id is not None:
            if admin_class_id not in se.admin_class_ids:
                continue
        for slot in se.timeslots:
            day, period = slot_to_day_period(slot)
            course  = inst.course(se.course_id)
            teacher = inst.teacher(se.teacher_id)
            room    = inst.classroom(se.classroom_id) if se.classroom_id else None
            label   = f"{course.code[:6]}/{teacher.name[:4]}"
            if room:
                label += f"/{room.name[:4]}"
            grid[period][day] = label[:12].ljust(12)

    header = "        " + "  ".join(d.ljust(12) for d in DAY_NAMES)
    rows   = []
    for p, row in enumerate(grid):
        rows.append(f"  {PERIOD_NAMES[p]}  " + "  ".join(row))

    return header + "\n" + "\n".join(rows)
