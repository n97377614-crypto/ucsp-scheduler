# UCSS — University Course Scheduling System

> **Graduation Project** — Faculty of Computer Science & Engineering, Galala University, 2026

A comprehensive intelligent scheduling platform that solves the University Course Scheduling Problem (UCSP) using a hybrid **POGA-DP** algorithm: a Progressively Optimized Genetic Algorithm for timeslot assignment combined with Dynamic Programming for classroom allocation.

---

## Algorithm Overview

The scheduler runs in three phases:

**Phase 1 — Joint Course Scheduling (GA)**
Joint courses (shared by multiple admin classes) are scheduled first, as they impose the most constraints. The GA uses tournament selection, crossover with a judgment mechanism, and forced mutation with a repair mechanism.

**Phase 2 — Independent Course Scheduling (GA)**
Independent courses are scheduled next, with Phase 1 assignments fixed, leaving the most flexible slots available.

**Phase 3 — Classroom Allocation (DP)**
Classrooms are assigned using Dynamic Programming that minimizes seat wastage while respecting room type and capacity constraints (paper §3.3, eq. 24).

### Constraints Enforced

| # | Type | Description |
|---|------|-------------|
| HC1 | Hard | No teacher double-booking |
| HC2 | Hard | No room double-booking |
| HC3 | Hard | No admin class double-booking |
| HC4 | Hard | Required weekly hours must be met |
| HC5 | Hard | Room capacity must fit student count |
| HC6 | Hard | Joint class coordination |
| HC7 | Hard | Room type must match course type |
| HC8 | Hard | Fixed slots must be respected |
| SC1 | Soft | Course distribution balance |
| SC2 | Soft | Admin class day balance |
| SC3 | Soft | Teacher day balance |
| SC4 | Soft | Teacher time preferences |
| SC5 | Soft | Room utilisation |

---

## Project Structure

```
UCSS/
├── api.py              # FastAPI REST API (all endpoints)
├── main.py             # CLI entry point
├── scheduler.py        # POGA-DP orchestrator (3-phase algorithm)
├── ga_engine.py        # Genetic Algorithm loop
├── operators.py        # Crossover + mutation operators
├── fitness.py          # Fitness function
├── constraints.py      # Hard & soft constraint checkers
├── dp_classroom.py     # DP classroom allocator
├── models.py           # All data models (Teacher, Room, Course, etc.)
├── sample_data.py      # Demo instances (Galala + 15 paper benchmarks)
├── src/                # React frontend source
│   ├── App.jsx
│   └── main.jsx
├── index.html
├── vite.config.js
├── package.json
└── ucsp-frontend/      # Standalone frontend (alternative entry)
```

---

## Requirements

- Python 3.10+
- Node.js 18+

---

## Setup & Run

### 1. Backend (FastAPI)

```bash
# Install dependencies
pip install fastapi uvicorn pydantic numpy

# Start the API server
python main.py --server

# API runs at:       http://localhost:8000
# Interactive docs:  http://localhost:8000/docs
```

### 2. Frontend (React + Vite)

```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# UI runs at: http://localhost:5173
```

### 3. Run CLI Demo (no UI needed)

```bash
# Galala University demo instance
python main.py

# Specific paper benchmark instance (1–15)
python main.py --instance 5 --gens 500

# Quick smoke test
python main.py --test
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | User authentication |
| POST | `/data/import/courses` | Bulk import courses |
| POST | `/instructors/{id}/avail` | Set instructor availability |
| POST | `/schedules/generate` | Trigger POGA-DP scheduler (async) |
| GET | `/schedules/jobs/{job_id}` | Poll job status |
| GET | `/schedules/{id}/view` | View schedule for one entity |
| GET | `/schedules/{id}/overview` | Full schedule overview |
| PATCH | `/schedules/{id}/adjust` | Manual slot adjustment |
| GET | `/schedules/compare` | Compare two schedule versions |
| GET | `/schedules/{id}/export` | Export as PDF / CSV / iCal |
| POST | `/instances/custom` | Upload custom university data |

Full interactive documentation available at `http://localhost:8000/docs` after starting the server.

---

## GA Parameters (Paper §4.1)

| Parameter | Value |
|-----------|-------|
| Max generations (Tmax) | 1000 |
| Population size | 50 |
| Crossover probability (Pc) | 0.8 |
| Mutation probability (Pm) | 0.01 |
| Tournament size (k) | 3 |
| Hard violation penalty | 10⁶ |

---

## References

Han & Wang (2025). *Algorithms*, 18(3), 158. — POGA-DP for University Course Scheduling.

---

## Team

Galala University — Computer Science & Engineering, Class of 2026
