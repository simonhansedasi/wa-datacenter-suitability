#!/usr/bin/env python3
"""
run_pipeline.py — Master script: runs all 7 siting analysis scripts in sequence.

Usage:
  python run_pipeline.py WA
  python run_pipeline.py OR --deploy       # run then show rsync reminder for DO deploy
  python run_pipeline.py TX --start 03     # resume from script 03 onward
  python run_pipeline.py CA --only 06 07   # run only specific scripts

Output: data/{STATE}/grid_scores.geojson (all 10 score columns)
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent

PIPELINE = [
    ("01", "01_basemap.py",    "State boundary, OSM data centers + transmission, EIA plants"),
    ("02", "02_indicators.py", "Fishnet grid + tx_score, water_score, ej_score"),
    ("03", "03_risk.py",       "seismic_score, flood_score"),
    ("04", "04_environment.py","contamination_score, waterway_score"),
    ("05", "05_geothermal.py", "geothermal_score"),
    ("06", "06_terrain.py",    "flatness_score (SRTM1 hard gate)"),
    ("07", "07_protected.py",  "protected_score (federal + tribal hard gate)"),
]


def run_step(script_file, state_abbr):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_file), state_abbr],
        check=False,
    )
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Run the data center siting pipeline for a US state.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py WA                 # full run
  python run_pipeline.py OR --deploy        # run + print rsync deploy reminder
  python run_pipeline.py TX --start 03      # resume from risk step
  python run_pipeline.py CA --only 06 07    # terrain + protected only
        """,
    )
    parser.add_argument("state", help="Two-letter state abbreviation (e.g. WA, OR, TX)")
    parser.add_argument("--deploy", action="store_true",
                        help="Copy grid_scores.geojson to static/ after completion")
    parser.add_argument("--start", metavar="NN", default="01",
                        help="Start from this step number (e.g. 03 to resume)")
    parser.add_argument("--only", nargs="+", metavar="NN",
                        help="Run only these step numbers (e.g. --only 06 07)")
    args = parser.parse_args()

    state_abbr = args.state.upper()

    # Determine which steps to run
    if args.only:
        steps = [s for s in PIPELINE if s[0] in args.only]
    else:
        steps = [s for s in PIPELINE if s[0] >= args.start]

    if not steps:
        print(f"No matching steps. Available: {[s[0] for s in PIPELINE]}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Data Center Siting Pipeline — {state_abbr}")
    print(f"  Steps: {[s[0] for s in steps]}")
    print(f"{'='*60}\n")

    for step_id, script_file, description in steps:
        print(f"\n{'─'*60}")
        print(f"  Step {step_id}: {description}")
        print(f"{'─'*60}")
        rc = run_step(script_file, state_abbr)
        if rc != 0:
            print(f"\nERROR: Step {step_id} ({script_file}) exited with code {rc}")
            print("Pipeline halted. Fix the error and re-run with --start", step_id)
            sys.exit(rc)

    # Deploy reminder: Flask reads from data/{STATE}/ directly; rsync to DO to publish
    if args.deploy:
        project_root = SCRIPTS_DIR.parent
        print(f"\nDeploy reminder — rsync data/{state_abbr}/ to DO:")
        print(f"  rsync -av --exclude='srtm_tiles' {project_root}/data/{state_abbr}/ "
              f"root@<DO_IP>:/path/to/datacenter_siting/data/{state_abbr}/")
        print("  Then restart: ssh root@<DO_IP> 'systemctl restart datacenters'")

    print(f"\n{'='*60}")
    print(f"  Pipeline complete for {state_abbr}.")
    grid_path_display = SCRIPTS_DIR.parent / "data" / state_abbr / "grid_scores.geojson"
    print(f"  Output: {grid_path_display}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
