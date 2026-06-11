"""
fitness.py
==========
Combined fitness function for the POGA-DP.

Formula (grad project Chapter 3 §3.6.3):
  fitness(schedule) = P_hard × violation_count(hard) + Σi wi × violation_score(soft_i)

  P_hard = 10^6  (prohibitively large — ensures feasibility beats any soft gain)

Paper fitness F1 (eqs 1-2, 17):
  F1 = Σt (Qt − Vt)     → used as SC4 component
  Vt = ω1·Σ(θτ²) + ω2·Tmax

OPTIMISATION DIRECTION: minimise.
A schedule with zero hard violations is always better than any infeasible one.
"""

from __future__ import annotations
from typing import Dict, Optional

from models import Chromosome, UCSPInstance
from constraints import (
    count_hard_violations,
    compute_soft_penalties,
)

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────
P_HARD: float = 1_000_000.0   # penalty per hard violation (grad project §3.6.3)

DEFAULT_WEIGHTS: Dict[str, float] = {
    "sc1": 0.5,   # course distribution
    "sc2": 1.0,   # admin class day balance
    "sc3": 1.0,   # teacher day balance
    "sc4": 1.0,   # teacher preferences (F1 of paper)
    "sc5": 0.3,   # room utilisation
}

# Paper §4.1: Chinese university preference weights
OMEGA1: float = 1.0   # penalty for consecutive classes
OMEGA2: float = 0.0   # ignore large gaps


def evaluate(chrom: Chromosome,
             inst: UCSPInstance,
             room_assignment: Dict[int, int] | None = None,
             weights: Dict[str, float] | None = None,
             omega1: float = OMEGA1,
             omega2: float = OMEGA2) -> float:
    """
    Evaluate one chromosome and return its fitness score (lower = better).

    Steps
    -----
    1. Count hard constraint violations  → heavy penalty
    2. Compute weighted soft penalties
    3. fitness = P_hard × hard_count + soft_total

    The room_assignment dict (event_id → classroom_id) is produced by the
    DP phase. If None (during pure GA time-slot search), HC2, HC5, HC7
    and SC5 are skipped.

    Example from grad project §3.6.3:
      2 hard violations, 15 gap-hours, 200 wasted seats →
        fitness = 10^6×2 + 0.5×15 + 0.3×200 = 2,000,067.5
      After fixing hard:
        fitness = 0 + 7.5 + 60 = 67.5
    """
    w = weights or DEFAULT_WEIGHTS

    hard_count = count_hard_violations(chrom, inst, room_assignment)
    soft_dict  = compute_soft_penalties(
        chrom, inst, room_assignment, omega1, omega2, w
    )

    fitness = P_HARD * hard_count + soft_dict["total"]
    chrom.fitness = fitness
    return fitness


def is_feasible(chrom: Chromosome, inst: UCSPInstance,
                room_assignment: Dict[int, int] | None = None) -> bool:
    """A schedule is feasible iff it has zero hard constraint violations."""
    return count_hard_violations(chrom, inst, room_assignment) == 0


def fitness_breakdown(chrom: Chromosome,
                       inst: UCSPInstance,
                       room_assignment: Dict[int, int] | None = None,
                       weights: Dict[str, float] | None = None) -> dict:
    """
    Return a human-readable breakdown of where penalty comes from.
    Useful for reporting and debugging.
    """
    from constraints import (
        hc1_teacher_conflict, hc3_class_conflict,
        hc4_required_hours,   hc6_joint_class_coordination,
        hc8_fixed_slots,
        hc2_room_conflict,    hc5_room_capacity,
        hc7_room_type_match,
    )

    ra = room_assignment or {}
    w  = weights or DEFAULT_WEIGHTS
    soft = compute_soft_penalties(chrom, inst, ra, OMEGA1, OMEGA2, w)

    hc_detail = {
        "hc1_teacher_conflict":   hc1_teacher_conflict(chrom, inst),
        "hc3_class_conflict":     hc3_class_conflict(chrom, inst),
        "hc4_required_hours":     hc4_required_hours(chrom, inst),
        "hc6_joint_coord":        hc6_joint_class_coordination(chrom, inst),
        "hc8_fixed_slots":        hc8_fixed_slots(chrom, inst),
    }
    if ra:
        hc_detail["hc2_room_conflict"] = hc2_room_conflict(chrom, inst, ra)
        hc_detail["hc5_room_capacity"] = hc5_room_capacity(inst, ra)
        hc_detail["hc7_room_type"]     = hc7_room_type_match(inst, ra)

    total_hard = sum(hc_detail.values())

    return {
        "feasible":   total_hard == 0,
        "fitness":    chrom.fitness,
        "hard_total": total_hard,
        "hard_detail": hc_detail,
        "soft_detail": soft,
        "hard_penalty": P_HARD * total_hard,
        "soft_penalty": soft["total"],
    }
