"""
main.py
=======
Command-line entry point for the UCSP POGA-DP scheduler.

Usage
-----
  # Run on the Galala University demo instance
  python main.py

  # Run on a specific paper benchmark instance (1-15)
  python main.py --instance 15 --gens 1000

  # Start the FastAPI server
  python main.py --server

  # Quick smoke test
  python main.py --test
"""

import argparse
import sys
import json

def run_demo(instance_name: str = "galala", instance_number: int = None,
             generations: int = 200, pop: int = 50, verbose: bool = True):
    """Run POGA-DP on an instance and print results."""
    from sample_data import build_galala_demo, get_paper_instance
    from ga_engine import GAConfig
    from scheduler import run_poga_dp, format_timetable

    if instance_number is not None:
        print(f"Loading paper Instance {instance_number}...")
        inst = get_paper_instance(instance_number)
    else:
        print("Loading Galala University demo instance...")
        inst = build_galala_demo()

    print(inst.summary())

    config = GAConfig(
        population_size = pop,
        max_generations = generations,
        crossover_prob  = 0.8,
        mutation_prob   = 0.01,
        tournament_k    = 3,
        omega1          = 1.0,
        omega2          = 0.0,
        time_limit_sec  = 600.0,
    )

    result = run_poga_dp(inst, config)

    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    print(result.summary())

    print("\nFitness breakdown:")
    bd = result.fitness_breakdown
    print(f"  Feasible:         {bd['feasible']}")
    print(f"  Total fitness:    {bd['fitness']:.2f}")
    print(f"  Hard violations:  {bd['hard_total']}")
    print(f"  Hard penalty:     {bd['hard_penalty']:.0f}")
    print(f"  Soft penalty:     {bd['soft_penalty']:.2f}")
    for k, v in bd.get("hard_detail", {}).items():
        if v:
            print(f"    {k}: {v}")
    print("\nSoft penalties:")
    for k, v in bd.get("soft_detail", {}).items():
        if k != "total":
            print(f"  {k}: {v:.3f}")

    print(f"\nClassroom utilisation:")
    ur = result.utilisation_report
    print(f"  Classrooms used:  {ur.get('classrooms_used', '?')}")
    print(f"  Avg occupancy:    {ur.get('occupancy', 0)*100:.1f}%")
    print(f"  Std dev:          {ur.get('std_dev', 0)*100:.2f}%")

    if verbose and result.feasible:
        print("\nSample timetable (first admin class):")
        if inst.admin_classes:
            first_class = inst.admin_classes[0]
            print(f"  {first_class.name}:")
            tt = format_timetable(result, inst, first_class.id)
            print(tt)

    # Phase histories
    if result.phase1_result:
        h = result.phase1_result.fitness_history
        print(f"\nPhase 1 GA: {len(h)} generations, "
              f"start={h[0]:.1f} → end={h[-1]:.1f}")
    if result.phase2_result:
        h = result.phase2_result.fitness_history
        print(f"Phase 2 GA: {len(h)} generations, "
              f"start={h[0]:.1f} → end={h[-1]:.1f}")

    return result


def run_tests():
    """
    Smoke test: run small instance, verify basic correctness.
    """
    print("Running smoke tests...")
    from sample_data import get_paper_instance
    from ga_engine import GAConfig
    from scheduler import run_poga_dp
    from fitness import is_feasible

    errors = []

    for inst_num in [1, 6, 11]:
        inst = get_paper_instance(inst_num, seed=0)
        config = GAConfig(population_size=20, max_generations=50)
        try:
            result = run_poga_dp(inst, config)
            print(f"  Instance {inst_num:2d}: fitness={result.final_fitness:.1f} "
                  f"feasible={result.feasible} rooms={result.classrooms_used}")
        except Exception as e:
            errors.append(f"Instance {inst_num}: {e}")
            print(f"  Instance {inst_num:2d}: ERROR – {e}")

    if errors:
        print(f"\n{len(errors)} test(s) failed:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("\nAll smoke tests passed.")


def start_server(host: str = "0.0.0.0", port: int = 8000):
    """Start the FastAPI server."""
    import uvicorn
    print(f"Starting UCSP API server on http://{host}:{port}")
    print(f"API docs: http://{host}:{port}/docs")
    uvicorn.run("api:app", host=host, port=port, reload=False)


def main():
    parser = argparse.ArgumentParser(
        description="UCSP POGA-DP Scheduler – Galala University"
    )
    parser.add_argument("--instance", type=int, default=None,
                        help="Paper instance number 1-15 (default: Galala demo)")
    parser.add_argument("--gens", type=int, default=200,
                        help="Number of GA generations (default: 200)")
    parser.add_argument("--pop", type=int, default=50,
                        help="Population size (default: 50)")
    parser.add_argument("--server", action="store_true",
                        help="Start the FastAPI REST API server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--test", action="store_true",
                        help="Run smoke tests")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress timetable output")

    args = parser.parse_args()

    if args.test:
        run_tests()
    elif args.server:
        start_server(port=args.port)
    else:
        run_demo(
            instance_number=args.instance,
            generations=args.gens,
            pop=args.pop,
            verbose=not args.quiet,
        )


if __name__ == "__main__":
    main()
