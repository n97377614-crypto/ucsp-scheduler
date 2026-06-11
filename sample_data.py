"""
sample_data.py
==============
Generates test instances matching Table 3 of the paper exactly:

  Instance 1-5:  small scale, independent courses only
  Instance 6-10: small scale, joint courses only
  Instance 11-15: large scale, mixed (high proportion of joint)

Table 3 from paper:
  Instance | Combined | Independent | Teachers | Total
  ---------|----------|-------------|----------|------
     1     |    0     |      6      |    5     |   6
     2     |    0     |     16      |    8     |  16
     3     |    0     |     26      |   13     |  26
     4     |    0     |     33      |   19     |  33
     5     |    0     |     57      |   38     |  57
     6     |   18     |      0      |    7     |  18
     7     |   42     |      0      |   16     |  42
     8     |  177     |      0      |   55     | 177
     9     |  302     |      0      |   92     | 302
    10     |  463     |      0      |  148     | 463
    11     |    5     |      6      |    8     |  11
    12     |   10     |      6      |   10     |  16
    13     |   42     |     16      |   24     |  58
    14     |  177     |     57      |   92     | 234
    15     |  463     |     57      |  176     | 520

Also generates a realistic "Galala University" instance for the grad project demo.
"""

from __future__ import annotations
import random
from typing import List

from models import (
    UCSPInstance, Teacher, Classroom, Course,
    AdminClass, TeachingClass, TeachingEvent,
    DEFAULT_PREFERENCES, SLOTS_PER_WEEK,
)


# ──────────────────────────────────────────────────────────────
# Internal ID counter
# ──────────────────────────────────────────────────────────────
class _IDCounter:
    def __init__(self): self._n = 0
    def next(self) -> int:
        self._n += 1; return self._n


# ──────────────────────────────────────────────────────────────
# Generic instance builder
# ──────────────────────────────────────────────────────────────

def build_instance(name: str,
                   n_joint: int,
                   n_independent: int,
                   n_teachers: int,
                   num_weeks: int = 20,
                   seed: int = 42) -> UCSPInstance:
    """
    Build one UCSP instance with the given counts.
    Classroom counts are auto-scaled to be realistic but slightly constrained.

    All randomness uses the given seed for reproducibility.
    """
    rng = random.Random(seed)
    inst = UCSPInstance(name=name, num_weeks=num_weeks)

    ids = _IDCounter()

    # ── Teachers ─────────────────────────────────────────────
    dept_names = ["CS", "Math", "Physics", "Chemistry", "Biology",
                  "English", "Economics", "Art", "Music", "History"]
    for i in range(n_teachers):
        dept = dept_names[i % len(dept_names)]
        pref = [
            [rng.choice([-2, 0, 1, 2, 3, 4, 6]) for _ in range(5)]
            for _ in range(5)
        ]
        inst.teachers.append(Teacher(
            id=ids.next(), name=f"T{i+1:03d}", department=dept,
            preference_table=pref,
        ))

    # ── Admin classes ─────────────────────────────────────────
    # Create enough admin classes to justify joint + independent events
    # Joint events need at least 2 admin classes per combined course.
    n_joint_admin_pairs = max(1, n_joint // 3)  # rough estimate
    n_admin = max(4, n_joint_admin_pairs * 2 + 2)
    for i in range(n_admin):
        inst.admin_classes.append(AdminClass(
            id=ids.next(), name=f"Class{i+1:02d}",
            program=f"Program{(i%4)+1}", year_level=(i%4)+1,
            student_count=rng.randint(20, 50),
        ))

    # ── Classrooms ────────────────────────────────────────────
    # Scale: roughly (total_events / 5) lecture rooms + a few labs
    total_events = n_joint + n_independent
    n_lecture_rooms = max(3, total_events // 8)
    n_lab_rooms     = max(1, total_events // 25)

    for i in range(n_lecture_rooms):
        cap = rng.choice([40, 60, 80, 100, 120, 150])
        inst.classrooms.append(Classroom(
            id=ids.next(), name=f"LH{i+1:03d}",
            capacity=cap, room_type="lecture",
            building=f"Bldg{(i%3)+1}",
        ))
    for i in range(n_lab_rooms):
        cap = rng.choice([20, 30, 40])
        inst.classrooms.append(Classroom(
            id=ids.next(), name=f"Lab{i+1:02d}",
            capacity=cap, room_type="lab",
            building="LabBlock",
        ))

    # ── Courses ───────────────────────────────────────────────
    course_types = ["lecture"] * 4 + ["lab"]
    n_courses = max(total_events // 2, 1)
    for i in range(n_courses):
        ctype = rng.choice(course_types)
        inst.courses.append(Course(
            id=ids.next(),
            code=f"C{i+1:04d}",
            name=f"Course {i+1}",
            weekly_hours=rng.choice([1, 2, 2]),
            course_type=ctype,
            credit_hours=rng.choice([2, 3, 3, 4]),
            department=rng.choice(dept_names),
            is_joint=(i < n_joint),
        ))

    teacher_ids = [t.id for t in inst.teachers]
    admin_ids   = [e.id for e in inst.admin_classes]

    # ── Teaching events ───────────────────────────────────────
    # Joint events
    for i in range(n_joint):
        course  = inst.courses[i % len(inst.courses)]
        teacher = rng.choice(inst.teachers)

        # Pick 2-3 admin classes to combine
        n_combined = rng.randint(2, min(3, len(admin_ids)))
        combined   = rng.sample(admin_ids, n_combined)
        combined_set = set(combined)
        total_stu = sum(
            e.student_count for e in inst.admin_classes if e.id in combined_set
        )

        tc = TeachingClass(id=ids.next(),
                           name=f"JTC{i+1}",
                           admin_class_ids=combined)
        inst.teaching_classes.append(tc)

        week_set = list(range(1, num_weeks + 1))
        lab_rids = [r.id for r in inst.classrooms if r.room_type == course.course_type]

        inst.teaching_events.append(TeachingEvent(
            id=ids.next(),
            course_id=course.id,
            teacher_id=teacher.id,
            teaching_class_id=tc.id,
            admin_class_ids=combined,
            weekly_hours=course.weekly_hours,
            week_set=week_set,
            total_students=total_stu,
            required_room_type=course.course_type,
            eligible_room_ids=lab_rids,
        ))

    # Independent events
    for i in range(n_independent):
        course  = inst.courses[(n_joint + i) % len(inst.courses)]
        teacher = rng.choice(inst.teachers)
        admin   = rng.choice(inst.admin_classes)

        tc = TeachingClass(id=ids.next(),
                           name=f"ITC{i+1}",
                           admin_class_ids=[admin.id])
        inst.teaching_classes.append(tc)

        week_set = list(range(1, num_weeks + 1))
        eligible = [r.id for r in inst.classrooms if r.room_type == course.course_type]

        inst.teaching_events.append(TeachingEvent(
            id=ids.next(),
            course_id=course.id,
            teacher_id=teacher.id,
            teaching_class_id=tc.id,
            admin_class_ids=[admin.id],
            weekly_hours=course.weekly_hours,
            week_set=week_set,
            total_students=admin.student_count,
            required_room_type=course.course_type,
            eligible_room_ids=eligible,
        ))

    inst.build_indices()
    return inst


# ──────────────────────────────────────────────────────────────
# All 15 paper instances
# ──────────────────────────────────────────────────────────────

PAPER_INSTANCES = [
    # (name,         n_joint, n_indep, n_teachers)
    ("Instance_01",  0,   6,  5),
    ("Instance_02",  0,  16,  8),
    ("Instance_03",  0,  26, 13),
    ("Instance_04",  0,  33, 19),
    ("Instance_05",  0,  57, 38),
    ("Instance_06", 18,   0,  7),
    ("Instance_07", 42,   0, 16),
    ("Instance_08",177,   0, 55),
    ("Instance_09",302,   0, 92),
    ("Instance_10",463,   0,148),
    ("Instance_11",  5,   6,  8),
    ("Instance_12", 10,   6, 10),
    ("Instance_13", 42,  16, 24),
    ("Instance_14",177,  57, 92),
    ("Instance_15",463,  57,176),
]


def get_paper_instance(number: int, seed: int = 42) -> UCSPInstance:
    """
    Get one of the 15 paper instances by number (1-15).
    Matches Table 3 of the paper exactly.
    """
    assert 1 <= number <= 15, "Instance number must be 1-15"
    name, jt, ind, tch = PAPER_INSTANCES[number - 1]
    return build_instance(name, jt, ind, tch, seed=seed)


def get_all_paper_instances(seed: int = 42) -> List[UCSPInstance]:
    return [get_paper_instance(i, seed) for i in range(1, 16)]


# ──────────────────────────────────────────────────────────────
# Galala University demo instance  (grad project scenario)
# ──────────────────────────────────────────────────────────────

def build_galala_demo() -> UCSPInstance:
    """
    A realistic demo instance inspired by the grad project at Galala University.

    Based on grad project §1.1: "Faculty of Computer Science and Engineering"
    - Roughly 3 year levels, each with 2 sections
    - Mix of CS, Math, Physics core courses
    - Some joint lectures (large classes share same professor)
    - Labs are independent per section
    """
    inst = UCSPInstance(name="Galala_CSE_Demo", num_weeks=16)
    ids  = _IDCounter()

    # ── Teachers ─────────────────────────────────────────────
    teacher_data = [
        ("Dr. Nora Niazy",      "CS"),
        ("Dr. Shaker Elsappagh","CS"),
        ("Prof. Ahmed Hassan",  "Math"),
        ("Dr. Sara Kamal",      "Physics"),
        ("Dr. Omar Fathy",      "CS"),
        ("Prof. Layla Ibrahim", "Math"),
        ("Dr. Yasser Mahmoud", "CS"),
        ("Dr. Mona Saad",      "English"),
        ("Prof. Tarek Ali",    "CS"),
        ("Dr. Hana Mostafa",   "Physics"),
    ]
    for name, dept in teacher_data:
        inst.teachers.append(Teacher(id=ids.next(), name=name, department=dept))

    # ── Admin Classes  (6 sections: Y1A,Y1B, Y2A,Y2B, Y3A,Y3B) ──────────
    sections = [
        ("Y1-A", "CSE", 1, 45), ("Y1-B", "CSE", 1, 42),
        ("Y2-A", "CSE", 2, 38), ("Y2-B", "CSE", 2, 40),
        ("Y3-A", "CSE", 3, 35), ("Y3-B", "CSE", 3, 33),
    ]
    for sname, prog, year, count in sections:
        inst.admin_classes.append(AdminClass(
            id=ids.next(), name=sname, program=prog,
            year_level=year, student_count=count,
        ))

    # ── Classrooms ───────────────────────────────────────────
    rooms = [
        ("LH-101", 100, "lecture"), ("LH-102", 80, "lecture"),
        ("LH-201", 60,  "lecture"), ("LH-202", 60, "lecture"),
        ("LH-301", 50,  "lecture"),
        ("Lab-CS1", 50, "lab"),     ("Lab-CS2", 50, "lab"),
        ("Lab-Phy1", 50, "lab"),    ("Lab-Phy2", 50, "lab"),
    ]
    for rname, cap, rtype in rooms:
        inst.classrooms.append(Classroom(
            id=ids.next(), name=rname, capacity=cap, room_type=rtype,
        ))

    # ── Courses ──────────────────────────────────────────────
    courses_data = [
        # code,       name,                       wh, type,      cr, dept
        ("CS101",  "Intro to Programming",         2, "lecture", 3, "CS"),
        ("CS102",  "Programming Lab",              2, "lab",     1, "CS"),
        ("MATH101","Calculus I",                   2, "lecture", 3, "Math"),
        ("PHYS101","Physics I",                    2, "lecture", 3, "Physics"),
        ("PHYS101L","Physics Lab",                 2, "lab",     1, "Physics"),
        ("CS201",  "Data Structures",              2, "lecture", 3, "CS"),
        ("CS202",  "DS Lab",                       2, "lab",     1, "CS"),
        ("MATH201","Linear Algebra",               2, "lecture", 3, "Math"),
        ("CS301",  "Algorithms",                   2, "lecture", 3, "CS"),
        ("CS302",  "Database Systems",             2, "lecture", 3, "CS"),
        ("CS303",  "AI Fundamentals",              2, "lecture", 3, "CS"),
        ("CS304",  "Networks",                     2, "lecture", 3, "CS"),
        ("ENG101", "Technical Writing",            2, "lecture", 2, "English"),
    ]
    course_objects = {}
    for code, cname, wh, ctype, cr, dept in courses_data:
        c = Course(id=ids.next(), code=code, name=cname,
                   weekly_hours=wh, course_type=ctype, credit_hours=cr,
                   department=dept)
        inst.courses.append(c)
        course_objects[code] = c

    # Get entity lookups
    T   = {t.name: t for t in inst.teachers}
    E   = {e.name: e for e in inst.admin_classes}
    C   = course_objects
    R   = inst.classrooms
    lec_rooms = [r.id for r in R if r.room_type == "lecture"]
    lab_rooms  = [r.id for r in R if r.room_type == "lab"]
    phy_labs   = [r.id for r in R if "Phy" in r.name]

    weeks_full   = list(range(1, 17))
    weeks_first  = list(range(1, 9))
    weeks_second = list(range(9, 17))

    def ev(cid, tid, tclass, admin_ids, weeks, rtype="lecture", rids=None):
        total_stu = sum(e.student_count for e in inst.admin_classes if e.id in admin_ids)
        tc = TeachingClass(id=ids.next(), name=f"TC{ids._n}",
                           admin_class_ids=admin_ids)
        inst.teaching_classes.append(tc)
        inst.teaching_events.append(TeachingEvent(
            id=ids.next(), course_id=cid,
            teacher_id=tid, teaching_class_id=tc.id,
            admin_class_ids=admin_ids,
            weekly_hours=inst._c.get(cid, Course(cid,"","",2)).weekly_hours
                if inst._c else 2,
            week_set=weeks,
            total_students=total_stu,
            required_room_type=rtype,
            eligible_room_ids=rids or [],
        ))

    inst.build_indices()   # build so we can use inst.course(id).weekly_hours

    def add_event(course_code, teacher_name, admin_class_names, weeks,
                  rtype=None, rids=None):
        c   = C[course_code]
        t   = T[teacher_name]
        ads = [E[n].id for n in admin_class_names]
        rt  = rtype or c.course_type
        total_stu = sum(E[n].student_count for n in admin_class_names)
        tc = TeachingClass(id=ids.next(), name=f"TC{len(inst.teaching_classes)+1}",
                           admin_class_ids=ads)
        inst.teaching_classes.append(tc)
        inst.teaching_events.append(TeachingEvent(
            id=ids.next(), course_id=c.id,
            teacher_id=t.id, teaching_class_id=tc.id,
            admin_class_ids=ads,
            weekly_hours=c.weekly_hours,
            week_set=weeks,
            total_students=total_stu,
            required_room_type=rt,
            eligible_room_ids=rids or (lec_rooms if rt == "lecture" else lab_rooms),
        ))

    # Year 1 — JOINT lecture (Y1A + Y1B together), independent labs
    add_event("CS101",   "Dr. Omar Fathy",       ["Y1-A","Y1-B"], weeks_full,  rids=lec_rooms)
    add_event("CS102",   "Dr. Omar Fathy",        ["Y1-A"],        weeks_full,  rtype="lab", rids=lab_rooms)
    add_event("CS102",   "Dr. Yasser Mahmoud",    ["Y1-B"],        weeks_full,  rtype="lab", rids=lab_rooms)
    add_event("MATH101", "Prof. Ahmed Hassan",    ["Y1-A","Y1-B"], weeks_full,  rids=lec_rooms)
    add_event("PHYS101", "Dr. Sara Kamal",        ["Y1-A","Y1-B"], weeks_full,  rids=lec_rooms)
    add_event("PHYS101L","Dr. Hana Mostafa",      ["Y1-A"],        weeks_full,  rtype="lab", rids=phy_labs)
    add_event("PHYS101L","Dr. Hana Mostafa",      ["Y1-B"],        weeks_full,  rtype="lab", rids=phy_labs)
    add_event("ENG101",  "Dr. Mona Saad",         ["Y1-A","Y1-B"], weeks_full,  rids=lec_rooms)

    # Year 2 — mix of joint and independent
    add_event("CS201",   "Dr. Nora Niazy",        ["Y2-A","Y2-B"], weeks_full,  rids=lec_rooms)
    add_event("CS202",   "Prof. Tarek Ali",        ["Y2-A"],        weeks_full,  rtype="lab", rids=lab_rooms)
    add_event("CS202",   "Prof. Tarek Ali",        ["Y2-B"],        weeks_full,  rtype="lab", rids=lab_rooms)
    add_event("MATH201", "Prof. Layla Ibrahim",   ["Y2-A","Y2-B"], weeks_full,  rids=lec_rooms)
    add_event("PHYS101", "Dr. Sara Kamal",        ["Y2-A"],        weeks_second,rids=lec_rooms)

    # Year 3 — all independent
    add_event("CS301",   "Dr. Nora Niazy",        ["Y3-A"],        weeks_full,  rids=lec_rooms)
    add_event("CS301",   "Dr. Shaker Elsappagh",  ["Y3-B"],        weeks_full,  rids=lec_rooms)
    add_event("CS302",   "Dr. Yasser Mahmoud",    ["Y3-A"],        weeks_full,  rids=lec_rooms)
    add_event("CS302",   "Dr. Yasser Mahmoud",    ["Y3-B"],        weeks_full,  rids=lec_rooms)
    add_event("CS303",   "Dr. Shaker Elsappagh",  ["Y3-A","Y3-B"], weeks_full,  rids=lec_rooms)
    add_event("CS304",   "Prof. Tarek Ali",        ["Y3-A","Y3-B"], weeks_full,  rids=lec_rooms)

    inst.build_indices()
    return inst
