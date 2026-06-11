"""
models.py
=========
All data structures for the University Course Scheduling Problem (UCSP).

References
----------
Grad project : "Comprehensive Intelligent Scheduling Platform", Galala Univ. 2026
Paper        : Han & Wang (2025) – Algorithms 18(3), 158.

Notation follows Table 1 of the paper.
  C  = courses            T  = teachers
  R  = classrooms         A  = course types
  D  = days (5)           W  = weeks (20)
  E  = admin classes      P  = teaching classes
  M  = teaching events    K  = weekly time slots (25)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────
# Global constants  (paper §2.1)
# ──────────────────────────────────────────────────────────────
DAYS_PER_WEEK    = 5
PERIODS_PER_DAY  = 5
SLOTS_PER_WEEK   = DAYS_PER_WEEK * PERIODS_PER_DAY   # 25

DAY_NAMES    = ["Mon", "Tue", "Wed", "Thu", "Fri"]
PERIOD_NAMES = ["P1",  "P2",  "P3",  "P4",  "P5"]

def slot_to_day_period(slot: int) -> Tuple[int, int]:
    return divmod(slot, PERIODS_PER_DAY)

def day_period_to_slot(day: int, period: int) -> int:
    return day * PERIODS_PER_DAY + period

# ──────────────────────────────────────────────────────────────
# Paper Table 2 – default teacher preference matrix
# preference_table[day 0-4][period 0-4]
# Higher = preferred; negative = disliked
# ──────────────────────────────────────────────────────────────
DEFAULT_PREFERENCES: List[List[int]] = [
    [ 1,  2,  4,  3,  0],  # Monday
    [ 3,  4,  6,  3,  0],  # Tuesday
    [ 2,  3, -2, -2, -2],  # Wednesday
    [-2, -2,  4,  4,  3],  # Thursday
    [ 6,  6,  5, -2, -2],  # Friday
]

# ──────────────────────────────────────────────────────────────
# Entities
# ──────────────────────────────────────────────────────────────

@dataclass
class Teacher:
    """t ∈ T.  Ct = course_ids.  Qt / Vt computed in fitness."""
    id:              int
    name:            str
    department:      str = ""
    max_daily_hours: int = 4
    course_ids:      List[int] = field(default_factory=list)
    preference_table: List[List[int]] = field(
        default_factory=lambda: [row[:] for row in DEFAULT_PREFERENCES]
    )

    def preference(self, slot: int) -> int:
        day, period = slot_to_day_period(slot)
        return self.preference_table[day][period]


@dataclass
class Classroom:
    """r ∈ R.  Nr = capacity.  ar = room_type (must match ac for HC7)."""
    id:        int
    name:      str
    capacity:  int           # Nr
    room_type: str = "lecture"
    building:  str = ""


@dataclass
class Course:
    """c ∈ C.  Bc = weekly_hours.  ac = course_type."""
    id:               int
    code:             str
    name:             str
    weekly_hours:     int  = 2          # Bc
    course_type:      str  = "lecture"  # ac
    credit_hours:     int  = 3
    department:       str  = ""
    is_joint:         bool = False
    eligible_room_ids: List[int] = field(default_factory=list)  # Rc


@dataclass
class AdminClass:
    """e ∈ E.  One student cohort.  Ye,d computed at runtime."""
    id:            int
    name:          str
    program:       str = ""
    year_level:    int = 1
    student_count: int = 30


@dataclass
class TeachingClass:
    """
    p ∈ P.  Groups one or more AdminClasses.
    For joint courses |Ep| > 1  →  Sp = size > 1  (paper eq. 8).
    """
    id:              int
    name:            str
    admin_class_ids: List[int] = field(default_factory=list)  # Ep

    @property
    def size(self) -> int:    # Sp
        return len(self.admin_class_ids)

    @property
    def is_joint(self) -> bool:
        return self.size > 1


@dataclass
class TeachingEvent:
    """
    m ∈ M.  The atomic unit the GA schedules.

    One (course, teacher, teaching_class) triple that needs:
      - a set of time slots k ∈ K  (one per weekly_hours)
      - a week_set Wm
      - a classroom (assigned by DP afterwards)

    xw,k,c in the paper  ≡  "this event is in week w, slot k".
    """
    id:                 int
    course_id:          int
    teacher_id:         int
    teaching_class_id:  int
    admin_class_ids:    List[int]   # Ep
    weekly_hours:       int = 2     # Bc (slots needed per week)
    week_set:           List[int] = field(default_factory=list)  # Wm
    fixed_slots:        List[int] = field(default_factory=list)  # HC8
    total_students:     int = 30
    required_room_type: str = "lecture"          # HC7
    eligible_room_ids:  List[int] = field(default_factory=list)

    @property
    def is_joint(self) -> bool:
        return len(self.admin_class_ids) > 1

    @property
    def is_fixed(self) -> bool:
        return bool(self.fixed_slots)


@dataclass
class ScheduledEvent:
    """
    Final output: one fully resolved assignment after both GA + DP.
    GA produces timeslots; DP adds the classroom.
    """
    event_id:        int
    course_id:       int
    teacher_id:      int
    admin_class_ids: List[int]
    timeslots:       List[int]      # flat 0-24
    week_set:        List[int]
    classroom_id:    Optional[int] = None

    def day_period_pairs(self) -> List[Tuple[int, int]]:
        return [slot_to_day_period(s) for s in self.timeslots]

    def as_dict(self) -> dict:
        pairs = self.day_period_pairs()
        return {
            "event_id":       self.event_id,
            "course_id":      self.course_id,
            "teacher_id":     self.teacher_id,
            "admin_classes":  self.admin_class_ids,
            "classroom_id":   self.classroom_id,
            "timeslots":      [
                {"slot": s, "day": DAY_NAMES[d], "period": PERIOD_NAMES[p]}
                for s, (d, p) in zip(self.timeslots, pairs)
            ],
            "weeks": self.week_set,
        }


# ──────────────────────────────────────────────────────────────
# Problem instance  (everything the algorithm needs)
# ──────────────────────────────────────────────────────────────

@dataclass
class UCSPInstance:
    """
    Complete description of one scheduling instance.
    Mirrors Table 3 of the paper (15 instances with varying
    proportions of joint vs independent courses).
    """
    name:             str = "instance"
    teachers:         List[Teacher]       = field(default_factory=list)
    classrooms:       List[Classroom]     = field(default_factory=list)
    courses:          List[Course]        = field(default_factory=list)
    admin_classes:    List[AdminClass]    = field(default_factory=list)
    teaching_classes: List[TeachingClass] = field(default_factory=list)
    teaching_events:  List[TeachingEvent] = field(default_factory=list)
    num_weeks:        int = 20

    # fast lookup (populated by build_indices)
    _t: Dict[int, Teacher]       = field(default_factory=dict, repr=False)
    _r: Dict[int, Classroom]     = field(default_factory=dict, repr=False)
    _c: Dict[int, Course]        = field(default_factory=dict, repr=False)
    _e: Dict[int, AdminClass]    = field(default_factory=dict, repr=False)
    _m: Dict[int, TeachingEvent] = field(default_factory=dict, repr=False)

    def build_indices(self) -> None:
        self._t = {x.id: x for x in self.teachers}
        self._r = {x.id: x for x in self.classrooms}
        self._c = {x.id: x for x in self.courses}
        self._e = {x.id: x for x in self.admin_classes}
        self._m = {x.id: x for x in self.teaching_events}

    def teacher(self, tid: int)    -> Teacher:       return self._t[tid]
    def classroom(self, rid: int)  -> Classroom:     return self._r[rid]
    def course(self, cid: int)     -> Course:        return self._c[cid]
    def admin_class(self, eid: int)-> AdminClass:    return self._e[eid]
    def event(self, mid: int)      -> TeachingEvent: return self._m[mid]

    def joint_events(self)       -> List[TeachingEvent]:
        return [m for m in self.teaching_events if m.is_joint]

    def independent_events(self) -> List[TeachingEvent]:
        return [m for m in self.teaching_events if not m.is_joint]

    def summary(self) -> str:
        j, i = len(self.joint_events()), len(self.independent_events())
        return (
            f"[{self.name}] events={len(self.teaching_events)} "
            f"(joint={j}, indep={i}), teachers={len(self.teachers)}, "
            f"rooms={len(self.classrooms)}, weeks={self.num_weeks}"
        )


# ──────────────────────────────────────────────────────────────
# Chromosome  (solution representation used by the GA)
# ──────────────────────────────────────────────────────────────

@dataclass
class Chromosome:
    """
    Figure 1 of the paper shows the chromosome as:
      S1 | S2 | ... | Sn
    where Si = 25 slots for admin class i.

    We store an equivalent representation: for each teaching event m,
    which time slots (0-24) are assigned to it this week.

      assignment[event_id] = [slot_0, slot_1, ...]   len = weekly_hours

    This is isomorphic to the paper's encoding but easier to manipulate
    in the swap and mutation operators.
    """
    assignment: Dict[int, List[int]] = field(default_factory=dict)
    fitness:    float = float("inf")   # lower = better

    def copy(self) -> Chromosome:
        return Chromosome(
            assignment={k: v[:] for k, v in self.assignment.items()},
            fitness=self.fitness,
        )

    def slots_for(self, event_id: int) -> List[int]:
        return self.assignment.get(event_id, [])

    def set_slots(self, event_id: int, slots: List[int]) -> None:
        self.assignment[event_id] = slots
