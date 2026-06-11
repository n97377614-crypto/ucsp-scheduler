"""
ga_engine.py
============
The Genetic Algorithm loop for the UCSP.

Implements the progressive optimization described in the paper and grad project:
  - Population initialisation
  - Fitness evaluation  (fitness.py)
  - Tournament selection
  - Crossover with judgment mechanism  (operators.py §3.2.2)
  - Forced mutation with repair mechanism  (operators.py §3.2.3)
  - Elitism: best individual always carried forward
  - Progress tracking (fitness per generation)

Parameters (paper §4.1):
  Tmax = 1000   max iterations
  Pm   = 0.01   mutation probability
  Pc   = 0.8    crossover probability
  tournament_k = 3  (standard practice for UCSP GAs)
  population_size = 50  (reasonable default; paper varies this)

Progressive optimization (grad project Chapter 4 §4.6):
  Early generations  (< 30% of Tmax): higher mutation, broader tournament
  Later generations  (≥ 70% of Tmax): lower mutation, tighter tournament
"""

from __future__ import annotations
import random
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from models import Chromosome, UCSPInstance, TeachingEvent
from fitness import evaluate
from operators import (
    crossover_with_judgment,
    mutate_with_repair,
    tournament_select,
    initialise_population,
)


# ──────────────────────────────────────────────────────────────
# GA Configuration
# ──────────────────────────────────────────────────────────────

@dataclass
class GAConfig:
    """All tunable parameters for one GA run."""
    population_size: int   = 50
    max_generations: int   = 1000    # Tmax
    crossover_prob:  float = 0.8     # Pc
    mutation_prob:   float = 0.01    # Pm
    tournament_k:    int   = 3
    elitism:         bool  = True    # always keep best solution
    # Soft-constraint weights (see fitness.py)
    sc_weights: Dict[str, float] = field(default_factory=lambda: {
        "sc1": 0.5, "sc2": 1.0, "sc3": 1.0, "sc4": 1.0, "sc5": 0.3,
    })
    omega1: float = 1.0   # consecutive-class penalty (paper §4.1)
    omega2: float = 0.0   # gap penalty (disabled for Chinese universities)
    # Progressive optimisation thresholds (grad project §4.6)
    explore_phase_ratio:  float = 0.30   # 0–30 % of Tmax = explore
    refine_phase_ratio:   float = 0.70   # 70–100 % = refine
    # Mutation rate scaling for progressive phases
    explore_mutation_mult: float = 3.0   # higher mutation in early phase
    refine_mutation_mult:  float = 0.5   # lower mutation in late phase
    # Maximum repair attempts per mutation
    max_repair_attempts: int = 10
    # Time limit in seconds (0 = no limit)
    time_limit_sec: float = 0.0


# ──────────────────────────────────────────────────────────────
# Run statistics
# ──────────────────────────────────────────────────────────────

@dataclass
class GAResult:
    """Everything the caller needs after a GA run."""
    best_chromosome: Chromosome
    best_fitness:    float
    fitness_history: List[float]      # best fitness per generation
    avg_history:     List[float]      # average fitness per generation
    generations_run: int
    elapsed_sec:     float
    feasible:        bool

    def summary(self) -> str:
        status = "FEASIBLE" if self.feasible else "INFEASIBLE"
        return (
            f"GA done | {status} | "
            f"best={self.best_fitness:.2f} | "
            f"gens={self.generations_run} | "
            f"time={self.elapsed_sec:.1f}s"
        )


# ──────────────────────────────────────────────────────────────
# Core GA loop
# ──────────────────────────────────────────────────────────────

def run_ga(events: List[TeachingEvent],
            inst: UCSPInstance,
            config: GAConfig,
            room_assignment: Dict[int, int] | None = None,
            progress_callback: Optional[Callable[[int, float], None]] = None
           ) -> GAResult:
    """
    Run the Genetic Algorithm on a given set of teaching events.

    Parameters
    ----------
    events           : events to schedule (joint or independent subset)
    inst             : full problem instance (for constraint checking)
    config           : GA hyper-parameters
    room_assignment  : optional classroom assignments from DP (for SC5)
    progress_callback: f(generation, best_fitness) called each generation

    Returns
    -------
    GAResult with the best chromosome found.
    """
    start_time = time.time()
    fitness_history: List[float] = []
    avg_history:     List[float] = []

    # ── Initialise population ─────────────────────────────────
    population = initialise_population(config.population_size, events, inst)

    # ── Evaluate initial population ───────────────────────────
    for chrom in population:
        evaluate(chrom, inst, room_assignment, config.sc_weights,
                 config.omega1, config.omega2)

    population.sort(key=lambda c: c.fitness)
    best = population[0].copy()

    fitness_history.append(best.fitness)
    avg_history.append(sum(c.fitness for c in population) / len(population))

    # ── Main loop ─────────────────────────────────────────────
    for gen in range(1, config.max_generations + 1):

        # Progressive optimisation: adapt mutation rate (grad project §4.6)
        phase_ratio = gen / config.max_generations
        if phase_ratio < config.explore_phase_ratio:
            # Early (explore): higher mutation for diversity
            pm = config.mutation_prob * config.explore_mutation_mult
            tk = max(2, config.tournament_k - 1)
        elif phase_ratio > config.refine_phase_ratio:
            # Late (refine): lower mutation to fine-tune
            pm = config.mutation_prob * config.refine_mutation_mult
            tk = config.tournament_k + 1
        else:
            pm = config.mutation_prob
            tk = config.tournament_k

        # ── Build next generation ─────────────────────────────
        next_pop: List[Chromosome] = []

        # Elitism: carry the best individual forward unchanged
        if config.elitism:
            next_pop.append(best.copy())

        while len(next_pop) < config.population_size:
            # Selection (tournament)
            parent_a = tournament_select(population, k=tk)
            parent_b = tournament_select(population, k=tk)

            # Crossover with judgment mechanism (paper §3.2.2)
            child_a, child_b = crossover_with_judgment(
                parent_a, parent_b, inst, config.crossover_prob
            )

            # Mutation with repair mechanism (paper §3.2.3)
            child_a = mutate_with_repair(child_a, inst, pm,
                                          config.max_repair_attempts)
            child_b = mutate_with_repair(child_b, inst, pm,
                                          config.max_repair_attempts)

            next_pop.append(child_a)
            if len(next_pop) < config.population_size:
                next_pop.append(child_b)

        population = next_pop

        # ── Evaluate new population ───────────────────────────
        for chrom in population:
            evaluate(chrom, inst, room_assignment, config.sc_weights,
                     config.omega1, config.omega2)

        population.sort(key=lambda c: c.fitness)

        # Update best
        if population[0].fitness < best.fitness:
            best = population[0].copy()

        # Track statistics
        fitness_history.append(best.fitness)
        avg_history.append(sum(c.fitness for c in population) / len(population))

        # Progress callback (for API polling)
        if progress_callback:
            progress_callback(gen, best.fitness)

        # Time limit check
        if config.time_limit_sec > 0:
            if time.time() - start_time >= config.time_limit_sec:
                break

        # Early stopping: perfect feasible solution found
        if best.fitness < 1.0:    # only soft penalties remain, negligible
            break

    elapsed = time.time() - start_time
    from fitness import is_feasible
    feasible = is_feasible(best, inst, room_assignment)

    return GAResult(
        best_chromosome=best,
        best_fitness=best.fitness,
        fitness_history=fitness_history,
        avg_history=avg_history,
        generations_run=len(fitness_history),
        elapsed_sec=elapsed,
        feasible=feasible,
    )
