#!/usr/bin/env python3
"""
run_zcta_study.py — Run the ZCTA-resolution study pipeline for a state.

Outputs to data/{STATE}/zcta/grid_scores.geojson (separate from the fishnet atlas).
Steps 03-07 from the parent pipeline are reused — they are geometry-agnostic.
The DC_SUBDIR=zcta env var tells config.get_paths() to read/write the zcta subdir.

Raw data (precip cache, transmission, state boundary) is shared with the fishnet run.
If the fishnet pipeline has already run for this state, step 02 is the only cold fetch.

Usage:
  conda activate GrapeExpectations
  python zcta/run_zcta_study.py WA
  python zcta/run_zcta_study.py WA --start 03   # resume after step 02
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
ZCTA_DIR = Path(__file__).parent

PIPELINE = [
    ("02", ZCTA_DIR / "02_zcta_indicators.py",  "ZCTA grid + tx_score, water_score, ej_score"),
    ("03", SCRIPTS_DIR / "03_risk.py",           "seismic_score, flood_score"),
    ("04", SCRIPTS_DIR / "04_environment.py",    "contamination_score, waterway_score"),
    ("05", SCRIPTS_DIR / "05_geothermal.py",     "geothermal_score"),
    ("06", SCRIPTS_DIR / "06_terrain.py",        "flatness_score (SRTM1 hard gate)"),
    ("07", SCRIPTS_DIR / "07_protected.py",      "protected_score (federal + tribal hard gate)"),
]


def run_step(script_path, state_abbr, step_id):
    env = os.environ.copy()
    if step_id != "02":
        env["DC_SUBDIR"] = "zcta"
    result = subprocess.run(
        [sys.executable, str(script_path), state_abbr],
        env=env,
        check=False,
    )
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Run the ZCTA study pipeline for a US state.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python zcta/run_zcta_study.py WA           # full ZCTA study run
  python zcta/run_zcta_study.py WA --start 03  # resume from risk step
        """,
    )
    parser.add_argument("state", help="Two-letter state abbreviation (e.g. WA)")
    parser.add_argument("--start", metavar="NN", default="02",
                        help="Start from this step number (default: 02)")
    args = parser.parse_args()

    state_abbr = args.state.upper()
    steps = [s for s in PIPELINE if s[0] >= args.start]

    if not steps:
        print(f"No matching steps. Available: {[s[0] for s in PIPELINE]}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  ZCTA Study Pipeline — {state_abbr}")
    print(f"  Output: data/{state_abbr}/zcta/grid_scores.geojson")
    print(f"  Steps: {[s[0] for s in steps]}")
    print(f"{'='*60}\n")

    for step_id, script_path, description in steps:
        print(f"\n{'─'*60}")
        print(f"  Step {step_id}: {description}")
        print(f"{'─'*60}")
        rc = run_step(script_path, state_abbr, step_id)
        if rc != 0:
            print(f"\nERROR: Step {step_id} exited with code {rc}")
            print(f"Fix the error and re-run with --start {step_id}")
            sys.exit(rc)

    print(f"\n{'='*60}")
    print(f"  ZCTA study complete for {state_abbr}.")
    print(f"  Output: data/{state_abbr}/zcta/grid_scores.geojson")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
