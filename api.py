"""
api.py
======
FastAPI REST API for the UCSP Scheduling Platform.

Endpoints match the grad project's Use Cases (Chapter 3 §3.3):
  UC1  POST /auth/login               – User authentication
  UC2  POST /data/import/courses      – Bulk import courses
  UC3  POST /instructors/{id}/avail   – Define availability
  UC4  POST /schedules/generate       – Trigger POGA-DP (async job)
  UC4  GET  /schedules/jobs/{job_id}  – Poll job status
  UC5  GET  /schedules/{id}/view      – Single-entity view
  UC6  GET  /schedules/{id}/overview  – Comprehensive view
  UC7  PATCH /schedules/{id}/adjust   – Manual adjustment
  UC8  GET  /schedules/compare        – Compare versions
  UC9  GET  /schedules/{id}/export    – Export (PDF/CSV/iCal)
  UC10 –    Notifications (Celery async, not exposed directly)
  NEW  POST /instances/custom         – Upload custom university data

This file is self-contained: it stores state in-memory for the demo.
In production, swap in PostgreSQL (SQLAlchemy) + Celery for async jobs.
"""

from __future__ import annotations
import uuid
import time
import threading
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from models import (
    UCSPInstance, Chromosome, DAYS_PER_WEEK, PERIODS_PER_DAY,
    DAY_NAMES, PERIOD_NAMES, slot_to_day_period,
    Teacher, Classroom, Course, AdminClass, TeachingClass, TeachingEvent,
)
from sample_data import build_galala_demo, get_paper_instance
from ga_engine import GAConfig
from scheduler import run_poga_dp, SchedulingResult, format_timetable
from fitness import fitness_breakdown


# ══════════════════════════════════════════════════════════════
#  App setup
# ══════════════════════════════════════════════════════════════

app = FastAPI(
    title="UCSP – Comprehensive Intelligent Scheduling Platform",
    description=(
        "Automated university course scheduling using POGA-DP "
        "(Progressively Optimized Genetic Algorithm with Dynamic Programming). "
        "Grad project – Faculty of Computer Science & Engineering, Galala University."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════
#  In-memory store  (replace with DB in production)
# ══════════════════════════════════════════════════════════════

class JobStatus(str, Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    CANCELLED = "CANCELLED"

class _Job:
    def __init__(self, job_id: str, instance_name: str):
        self.job_id         = job_id
        self.instance_name  = instance_name
        self.status         = JobStatus.PENDING
        self.progress: dict = {"phase": "", "generation": 0, "best_fitness": None}
        self.result: Optional[SchedulingResult] = None
        self.error: str     = ""
        self.created_at     = time.time()
        self.completed_at: Optional[float] = None

_JOBS:      Dict[str, _Job]             = {}
_INSTANCES: Dict[str, UCSPInstance]     = {}
_RESULTS:   Dict[str, SchedulingResult] = {}

# Pre-load the Galala demo on startup
_galala = build_galala_demo()
_INSTANCES["galala_demo"] = _galala


# ══════════════════════════════════════════════════════════════
#  Pydantic schemas
# ══════════════════════════════════════════════════════════════

class GenerateRequest(BaseModel):
    instance_name:   str   = "galala_demo"
    population_size: int   = 50
    max_generations: int   = 200
    crossover_prob:  float = 0.8
    mutation_prob:   float = 0.01
    tournament_k:    int   = 3
    omega1:          float = 1.0
    omega2:          float = 0.0
    sc_weights: Dict[str, float] = {
        "sc1": 0.5, "sc2": 1.0, "sc3": 1.0, "sc4": 1.0, "sc5": 0.3,
    }
    time_limit_sec:  float = 300.0


class AdjustRequest(BaseModel):
    event_id: int
    new_slots: List[int]


class LoadPaperInstanceRequest(BaseModel):
    instance_number: int  # 1-15


# ── Custom instance upload schemas ────────────────────────────

class TeacherIn(BaseModel):
    id: int
    name: str
    department: str = ""
    max_daily_hours: int = 4

class ClassroomIn(BaseModel):
    id: int
    name: str
    capacity: int
    room_type: str = "lecture"

class CourseIn(BaseModel):
    id: int
    code: str
    name: str
    weekly_hours: int = 2
    course_type: str = "lecture"
    credit_hours: int = 3
    department: str = ""

class AdminClassIn(BaseModel):
    id: int
    name: str
    program: str = ""
    year_level: int = 1
    student_count: int = 30

class TeachingEventIn(BaseModel):
    id: int
    course_id: int
    teacher_id: int
    admin_class_ids: List[int]
    weekly_hours: int = 2
    week_set: List[int] = []
    total_students: int = 0
    required_room_type: str = "lecture"
    eligible_room_ids: List[int] = []

class CustomInstanceRequest(BaseModel):
    name: str
    num_weeks: int = 20
    teachers: List[TeacherIn]
    classrooms: List[ClassroomIn]
    courses: List[CourseIn]
    admin_classes: List[AdminClassIn]
    teaching_events: List[TeachingEventIn]


# ══════════════════════════════════════════════════════════════
#  Helper
# ══════════════════════════════════════════════════════════════

def _result_to_dict(result: SchedulingResult, inst: UCSPInstance) -> dict:
    events = []
    for se in result.scheduled_events:
        course    = inst.course(se.course_id)
        teacher   = inst.teacher(se.teacher_id)
        room_name = (inst.classroom(se.classroom_id).name
                     if se.classroom_id else "UNASSIGNED")
        admin_names = [inst.admin_class(eid).name for eid in se.admin_class_ids]
        events.append({
            "event_id":      se.event_id,
            "course_code":   course.code,
            "course_name":   course.name,
            "teacher":       teacher.name,
            "admin_classes": admin_names,
            "classroom":     room_name,
            "timeslots": [
                {
                    "slot":   s,
                    "day":    DAY_NAMES[slot_to_day_period(s)[0]],
                    "period": PERIOD_NAMES[slot_to_day_period(s)[1]],
                }
                for s in se.timeslots
            ],
            "weeks": se.week_set,
        })
    return {
        "feasible":          result.feasible,
        "final_fitness":     result.final_fitness,
        "hard_violations":   result.hard_violations,
        "classrooms_used":   result.classrooms_used,
        "occupancy_pct":     round(result.occupancy * 100, 2),
        "fitness_breakdown": result.fitness_breakdown,
        "utilisation":       result.utilisation_report,
        "scheduled_events":  events,
        "phase1_fitness_history": (
            result.phase1_result.fitness_history if result.phase1_result else []
        ),
        "phase2_fitness_history": (
            result.phase2_result.fitness_history if result.phase2_result else []
        ),
    }


# ══════════════════════════════════════════════════════════════
#  Endpoints
# ══════════════════════════════════════════════════════════════

@app.get("/", tags=["root"])
def root():
    return {
        "project":   "Comprehensive Intelligent Scheduling Platform",
        "algorithm": "POGA-DP",
        "university": "Galala University",
        "docs":      "/docs",
        "upload_ui": "/upload",
    }


# ── Upload UI (served as HTML page) ──────────────────────────

@app.get("/upload", response_class=HTMLResponse, tags=["upload"])
def upload_ui():
    """Serve the data upload HTML interface."""
    with open("upload.html", "r", encoding="utf-8") as f:
        return f.read()


# ── Instance management ───────────────────────────────────────

@app.get("/instances", tags=["instances"])
def list_instances():
    """List all loaded instances."""
    return {
        "instances": [
            {"name": name, "summary": inst.summary()}
            for name, inst in _INSTANCES.items()
        ]
    }


@app.post("/instances/paper", tags=["instances"])
def load_paper_instance(body: LoadPaperInstanceRequest):
    """
    Load one of the 15 benchmark instances from the paper (Table 3).
    Instance numbers 1-15.
    """
    n = body.instance_number
    if not (1 <= n <= 15):
        raise HTTPException(400, "Instance number must be 1-15")
    inst = get_paper_instance(n)
    _INSTANCES[inst.name] = inst
    return {"loaded": inst.name, "summary": inst.summary()}


@app.post("/instances/custom", tags=["instances"])
def load_custom_instance(body: CustomInstanceRequest):
    """
    Upload your own university data and register it as a schedulable instance.

    Required fields per entity:
      teachers      : id, name, department
      classrooms    : id, name, capacity, room_type ("lecture" | "lab")
      courses       : id, code, name, weekly_hours, course_type
      admin_classes : id, name, student_count
      teaching_events: id, course_id, teacher_id, admin_class_ids,
                       weekly_hours, required_room_type, total_students

    All IDs must be unique integers. Every course_id / teacher_id /
    admin_class_id referenced in teaching_events must exist above.
    """
    # Validate all referenced IDs exist
    teacher_ids  = {t.id for t in body.teachers}
    course_ids   = {c.id for c in body.courses}
    aclass_ids   = {a.id for a in body.admin_classes}

    for ev in body.teaching_events:
        if ev.teacher_id not in teacher_ids:
            raise HTTPException(400, f"Event {ev.id}: teacher_id {ev.teacher_id} not found")
        if ev.course_id not in course_ids:
            raise HTTPException(400, f"Event {ev.id}: course_id {ev.course_id} not found")
        for aid in ev.admin_class_ids:
            if aid not in aclass_ids:
                raise HTTPException(400, f"Event {ev.id}: admin_class_id {aid} not found")

    inst = UCSPInstance(name=body.name, num_weeks=body.num_weeks)

    inst.teachers = [
        Teacher(id=t.id, name=t.name, department=t.department,
                max_daily_hours=t.max_daily_hours)
        for t in body.teachers
    ]
    inst.classrooms = [
        Classroom(id=r.id, name=r.name, capacity=r.capacity, room_type=r.room_type)
        for r in body.classrooms
    ]
    inst.courses = [
        Course(id=c.id, code=c.code, name=c.name, weekly_hours=c.weekly_hours,
               course_type=c.course_type, credit_hours=c.credit_hours,
               department=c.department)
        for c in body.courses
    ]
    inst.admin_classes = [
        AdminClass(id=a.id, name=a.name, program=a.program,
                   year_level=a.year_level, student_count=a.student_count)
        for a in body.admin_classes
    ]

    weeks_default = list(range(1, body.num_weeks + 1))
    aclass_map = {a.id: a for a in inst.admin_classes}

    for ev in body.teaching_events:
        tc = TeachingClass(
            id=ev.id * 10000,
            name=f"TC_{ev.id}",
            admin_class_ids=ev.admin_class_ids,
        )
        inst.teaching_classes.append(tc)

        # Auto-compute total_students if not provided
        total_stu = ev.total_students or sum(
            aclass_map[aid].student_count
            for aid in ev.admin_class_ids
            if aid in aclass_map
        )

        inst.teaching_events.append(TeachingEvent(
            id=ev.id,
            course_id=ev.course_id,
            teacher_id=ev.teacher_id,
            teaching_class_id=tc.id,
            admin_class_ids=ev.admin_class_ids,
            weekly_hours=ev.weekly_hours,
            week_set=ev.week_set or weeks_default,
            total_students=total_stu,
            required_room_type=ev.required_room_type,
            eligible_room_ids=ev.eligible_room_ids,
        ))

    inst.build_indices()
    _INSTANCES[body.name] = inst

    return {
        "loaded":  body.name,
        "summary": inst.summary(),
        "counts": {
            "teachers":       len(inst.teachers),
            "classrooms":     len(inst.classrooms),
            "courses":        len(inst.courses),
            "admin_classes":  len(inst.admin_classes),
            "teaching_events": len(inst.teaching_events),
            "joint_events":   len(inst.joint_events()),
            "indep_events":   len(inst.independent_events()),
        },
    }


@app.get("/instances/{name}", tags=["instances"])
def get_instance_info(name: str):
    """Get details of a loaded instance."""
    inst = _INSTANCES.get(name)
    if not inst:
        raise HTTPException(404, f"Instance '{name}' not found")
    return {
        "name":             inst.name,
        "summary":          inst.summary(),
        "num_teachers":     len(inst.teachers),
        "num_classrooms":   len(inst.classrooms),
        "num_courses":      len(inst.courses),
        "num_admin_classes": len(inst.admin_classes),
        "num_events":       len(inst.teaching_events),
        "joint_events":     len(inst.joint_events()),
        "indep_events":     len(inst.independent_events()),
        "teachers":     [{"id": t.id, "name": t.name, "dept": t.department}
                         for t in inst.teachers],
        "classrooms":   [{"id": r.id, "name": r.name, "capacity": r.capacity,
                           "type": r.room_type} for r in inst.classrooms],
        "admin_classes": [{"id": e.id, "name": e.name, "students": e.student_count}
                           for e in inst.admin_classes],
    }


# ── UC4: Schedule generation ──────────────────────────────────

@app.post("/schedules/generate", tags=["scheduling"])
def generate_schedule(body: GenerateRequest, background_tasks: BackgroundTasks):
    """
    UC4: Trigger asynchronous POGA-DP schedule generation.
    Returns a job_id immediately. Poll /schedules/jobs/{job_id} for status.
    """
    inst = _INSTANCES.get(body.instance_name)
    if not inst:
        raise HTTPException(
            404,
            f"Instance '{body.instance_name}' not found. "
            f"Upload it first via POST /instances/custom, "
            f"or load a paper instance via POST /instances/paper. "
            f"Available: {list(_INSTANCES.keys())}"
        )

    job_id = str(uuid.uuid4())[:8]
    job    = _Job(job_id, body.instance_name)
    _JOBS[job_id] = job

    config = GAConfig(
        population_size = body.population_size,
        max_generations = body.max_generations,
        crossover_prob  = body.crossover_prob,
        mutation_prob   = body.mutation_prob,
        tournament_k    = body.tournament_k,
        sc_weights      = body.sc_weights,
        omega1          = body.omega1,
        omega2          = body.omega2,
        time_limit_sec  = body.time_limit_sec,
    )

    def _run():
        job.status = JobStatus.RUNNING

        def progress(phase: str, gen: int, fitness: float):
            job.progress = {"phase": phase, "generation": gen,
                            "best_fitness": fitness}

        try:
            result = run_poga_dp(inst, config, progress_callback=progress)
            _RESULTS[job_id] = result
            job.result  = result
            job.status  = JobStatus.COMPLETED
        except Exception as exc:
            job.error  = str(exc)
            job.status = JobStatus.FAILED
        finally:
            job.completed_at = time.time()

    background_tasks.add_task(_run)

    return {
        "job_id":  job_id,
        "status":  job.status,
        "message": "Generation started. Poll /schedules/jobs/{job_id} for progress.",
        "config":  {
            "instance":        body.instance_name,
            "population":      body.population_size,
            "max_generations": body.max_generations,
        },
    }


@app.get("/schedules/jobs/{job_id}", tags=["scheduling"])
def poll_job(job_id: str):
    """UC4: Poll schedule generation progress."""
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")

    resp: dict = {
        "job_id":   job_id,
        "status":   job.status,
        "progress": job.progress,
        "instance": job.instance_name,
        "elapsed":  round(time.time() - job.created_at, 1),
    }

    if job.status == JobStatus.COMPLETED and job.result:
        inst = _INSTANCES.get(job.instance_name)
        resp["result"]  = _result_to_dict(job.result, inst) if inst else {}
        resp["summary"] = job.result.summary()

    if job.status == JobStatus.FAILED:
        resp["error"] = job.error

    return resp


@app.get("/schedules/jobs", tags=["scheduling"])
def list_jobs():
    """List all generation jobs and their statuses."""
    return {
        "jobs": [
            {
                "job_id":   jid,
                "status":   j.status,
                "instance": j.instance_name,
                "elapsed":  round(time.time() - j.created_at, 1),
            }
            for jid, j in _JOBS.items()
        ]
    }


# ── UC5/UC6: View schedules ───────────────────────────────────

@app.get("/schedules/{job_id}/timetable", tags=["viewing"])
def get_timetable(job_id: str,
                  admin_class_name: Optional[str] = Query(None),
                  format: str = Query("json", description="json or text")):
    """
    UC5: View schedule for one admin class.
    UC6: View all (if admin_class_name is omitted).
    """
    job = _JOBS.get(job_id)
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(404, "Job not found or not yet complete")

    inst   = _INSTANCES[job.instance_name]
    result = _RESULTS[job_id]

    if format == "text":
        aid = None
        if admin_class_name:
            matches = [e for e in inst.admin_classes if e.name == admin_class_name]
            if not matches:
                raise HTTPException(404, f"Admin class '{admin_class_name}' not found")
            aid = matches[0].id
        return {"timetable": format_timetable(result, inst, aid)}

    events = result.scheduled_events
    if admin_class_name:
        matches = [e for e in inst.admin_classes if e.name == admin_class_name]
        if not matches:
            raise HTTPException(404, f"Admin class '{admin_class_name}' not found")
        aid = matches[0].id
        events = [se for se in events if aid in se.admin_class_ids]

    grid = [[{} for _ in range(DAYS_PER_WEEK)] for _ in range(PERIODS_PER_DAY)]
    for se in events:
        c  = inst.course(se.course_id)
        t  = inst.teacher(se.teacher_id)
        rn = inst.classroom(se.classroom_id).name if se.classroom_id else "?"
        for slot in se.timeslots:
            day, period = slot_to_day_period(slot)
            grid[period][day] = {
                "course":  c.code,
                "teacher": t.name,
                "room":    rn,
                "joint":   len(se.admin_class_ids) > 1,
            }

    return {
        "admin_class": admin_class_name or "ALL",
        "grid": [
            {
                "period": PERIOD_NAMES[p],
                "days":   {DAY_NAMES[d]: grid[p][d] for d in range(DAYS_PER_WEEK)}
            }
            for p in range(PERIODS_PER_DAY)
        ],
        "events_count": len(events),
    }


# ── UC7: Manual adjustment ────────────────────────────────────

@app.patch("/schedules/{job_id}/adjust", tags=["adjustment"])
def manual_adjust(job_id: str, body: AdjustRequest):
    """
    UC7: Manually move one event to new time slots.
    Validates against hard constraints and returns any conflicts.
    """
    job = _JOBS.get(job_id)
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(404, "Job not found or not complete")

    inst   = _INSTANCES[job.instance_name]
    result = _RESULTS[job_id]
    chrom  = result.chromosome

    event_ids = {ev.id for ev in inst.teaching_events}
    if body.event_id not in event_ids:
        raise HTTPException(404, f"Event {body.event_id} not found")

    event = inst.event(body.event_id)

    if len(body.new_slots) != event.weekly_hours:
        raise HTTPException(
            400, f"Event needs {event.weekly_hours} slot(s), got {len(body.new_slots)}"
        )
    if any(s < 0 or s >= 25 for s in body.new_slots):
        raise HTTPException(400, "Slots must be in range 0-24")
    if len(set(body.new_slots)) != len(body.new_slots):
        raise HTTPException(400, "Slots must be distinct")

    old_slots = chrom.slots_for(body.event_id)
    chrom.set_slots(body.event_id, body.new_slots)

    from fitness import evaluate
    evaluate(chrom, inst, result.room_assignment, {})
    bd = fitness_breakdown(chrom, inst, result.room_assignment)

    conflicts = [
        f"{k}: {v} violation(s)"
        for k, v in bd["hard_detail"].items() if v > 0
    ]

    _RESULTS[job_id] = result

    return {
        "applied":     True,
        "event_id":    body.event_id,
        "old_slots":   old_slots,
        "new_slots":   body.new_slots,
        "conflicts":   conflicts,
        "feasible":    bd["feasible"],
        "new_fitness": chrom.fitness,
    }


# ── UC8: Compare schedule versions ───────────────────────────

@app.get("/schedules/compare", tags=["comparison"])
def compare_schedules(job_ids: str = Query(..., description="Comma-separated job IDs")):
    """UC8: Compare two or more schedule versions side-by-side."""
    ids = [j.strip() for j in job_ids.split(",")]
    if len(ids) < 2:
        raise HTTPException(400, "Provide at least 2 job IDs separated by comma")

    comparison = []
    for jid in ids:
        job = _JOBS.get(jid)
        if not job or job.status != JobStatus.COMPLETED:
            raise HTTPException(404, f"Job '{jid}' not found or not complete")
        r = _RESULTS[jid]
        comparison.append({
            "job_id":          jid,
            "instance":        job.instance_name,
            "feasible":        r.feasible,
            "fitness":         r.final_fitness,
            "hard_violations": r.hard_violations,
            "classrooms_used": r.classrooms_used,
            "occupancy_pct":   round(r.occupancy * 100, 2),
            "soft_sc1":        r.fitness_breakdown.get("soft_detail", {}).get("sc1", 0),
            "soft_sc2":        r.fitness_breakdown.get("soft_detail", {}).get("sc2", 0),
            "soft_sc3":        r.fitness_breakdown.get("soft_detail", {}).get("sc3", 0),
            "soft_sc4":        r.fitness_breakdown.get("soft_detail", {}).get("sc4", 0),
        })

    ranked = sorted(comparison, key=lambda x: x["fitness"])
    for i, item in enumerate(ranked):
        item["rank"] = i + 1

    return {"comparison": ranked, "best_job_id": ranked[0]["job_id"]}


# ── UC9: Export ───────────────────────────────────────────────

@app.get("/schedules/{job_id}/export/csv", tags=["export"])
def export_csv(job_id: str):
    """UC9: Export schedule as CSV."""
    from fastapi.responses import Response
    job = _JOBS.get(job_id)
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(404, "Job not complete")

    inst   = _INSTANCES[job.instance_name]
    result = _RESULTS[job_id]

    rows = ["Event ID,Course Code,Course Name,Teacher,Admin Classes,"
            "Day,Period,Slot,Classroom,Weeks"]
    for se in result.scheduled_events:
        c       = inst.course(se.course_id)
        t       = inst.teacher(se.teacher_id)
        rn      = inst.classroom(se.classroom_id).name if se.classroom_id else "UNASSIGNED"
        classes = "|".join(inst.admin_class(eid).name for eid in se.admin_class_ids)
        weeks   = "|".join(str(w) for w in se.week_set)
        for slot in se.timeslots:
            day, period = slot_to_day_period(slot)
            rows.append(
                f"{se.event_id},{c.code},{c.name},{t.name},{classes},"
                f"{DAY_NAMES[day]},{PERIOD_NAMES[period]},{slot},{rn},{weeks}"
            )

    return Response(
        content="\n".join(rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="schedule_{job_id}.csv"'},
    )


@app.get("/schedules/{job_id}/export/json", tags=["export"])
def export_json(job_id: str):
    """UC9: Export full schedule as JSON."""
    job = _JOBS.get(job_id)
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(404, "Job not complete")
    inst   = _INSTANCES[job.instance_name]
    result = _RESULTS[job_id]
    return _result_to_dict(result, inst)


# ── Health & metadata ─────────────────────────────────────────

@app.get("/health", tags=["meta"])
def health():
    return {
        "status":    "ok",
        "jobs":      len(_JOBS),
        "instances": len(_INSTANCES),
        "instance_names": list(_INSTANCES.keys()),
    }


@app.get("/config/defaults", tags=["meta"])
def get_defaults():
    """Return the default GA parameters (paper §4.1)."""
    return {
        "algorithm": "POGA-DP",
        "paper":     "Han & Wang (2025), Algorithms 18(3), 158",
        "parameters": {
            "population_size": 50,
            "max_generations": 1000,
            "crossover_prob":  0.8,
            "mutation_prob":   0.01,
            "tournament_k":    3,
            "omega1":          1.0,
            "omega2":          0.0,
        },
        "hard_constraint_penalty": 1_000_000,
        "soft_weights": {"sc1": 0.5, "sc2": 1.0, "sc3": 1.0, "sc4": 1.0, "sc5": 0.3},
        "phases": [
            "Phase 1: GA on joint (combined) courses",
            "Phase 2: GA on independent courses",
            "Phase 3: DP classroom allocation",
        ],
    }
