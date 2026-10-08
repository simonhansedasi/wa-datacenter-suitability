"""
09_soil.py — Compute soil permeability score from USDA SSURGO hydrologic soil group.

Adds to grid_scores.geojson:
  soil_score — 0-1 (high = low permeability = low spill percolation risk to groundwater)

Method:
  - Fetches mukey → hydgrpdcd mapping via SDM tabular REST service
    (mapunit ⋈ muaggatt ⋈ legend; filter areasymbol LIKE '{STATE}%')
  - Fetches one representative mupolygon location per mukey (SELECT * by mupolygonkey)
  - Parses first coordinate from WKT geographic column (col6)
  - Maps hydrologic group to numeric score:
      A → 0.00  (high permeability, highest contamination risk)
      B → 0.33
      C → 0.67
      D → 1.00  (low permeability, lowest contamination risk)
      A/D, B/D, C/D → split-class midpoints
  - IDW interpolation (k=8, power=2) from mukey representative points to grid centroids

Rationale: high-permeability soils (Group A) allow surface spills to reach groundwater
quickly; low-permeability soils (Group D) reduce that pathway.

Usage:
  python 09_soil.py WA
"""

import argparse
import re
import sys
import time
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from config import get_state, get_paths

warnings.filterwarnings("ignore")
CRS    = "EPSG:4326"
DARK_BG = "#1a1a2e"
WHITE  = "white"

SDM_URL   = "https://SDMDataAccess.sc.egov.usda.gov/Tabular/SDMTabularService/post.rest"
SDM_HDR   = {"Content-Type": "application/json"}
BATCH     = 100     # mupolygonkeys per API call
IDW_K     = 8
IDW_POWER = 2

# Hydrologic group → soil_score (high = low permeability = low contamination risk)
HYDGRP_SCORE = {
    "A":   0.00,
    "B":   0.33,
    "C":   0.67,
    "D":   1.00,
    "A/D": 0.50,
    "B/D": 0.67,
    "C/D": 0.83,
}


# ── SDM helpers ────────────────────────────────────────────────────────────────

def sdm_query(q, timeout=120):
    r = requests.post(SDM_URL, headers=SDM_HDR, json={"query": q, "FORMAT": "JSON"}, timeout=timeout)
    r.raise_for_status()
    return requests.models.Response.json(r).get("Table", [])


def fetch_mukey_hydgrp(state_abbr, cache_path):
    """Get all mukeys + hydgrpdcd + one representative mupolygonkey per mukey."""
    if cache_path.exists():
        df = pd.read_csv(cache_path)
        print(f"  Loaded {len(df)} mukeys from cache")
        return df

    abbr = state_abbr.upper()
    print(f"  Querying SDM for {abbr} mukey-hydgrp-polykey...")
    q = f"""SELECT mapunit.mukey, muaggatt.hydgrpdcd, MIN(mupolygon.mupolygonkey) AS poly_id
FROM mupolygon
INNER JOIN mapunit ON mupolygon.mukey=mapunit.mukey
INNER JOIN legend ON mapunit.lkey=legend.lkey
INNER JOIN muaggatt ON mapunit.mukey=muaggatt.mukey
WHERE legend.areasymbol LIKE '{abbr}%' AND muaggatt.hydgrpdcd IS NOT NULL
GROUP BY mapunit.mukey, muaggatt.hydgrpdcd"""

    rows = sdm_query(q, timeout=120)
    print(f"  Got {len(rows)} mukeys with hydgrpdcd")

    df = pd.DataFrame(rows, columns=["mukey", "hydgrpdcd", "poly_id"])
    df.to_csv(cache_path, index=False)
    print(f"  Cached to {cache_path.name}")
    return df


def fetch_poly_coords(df_mukeys, cache_path):
    """Batch-fetch one mupolygon WKT per mukey; parse first lon/lat from geographic WKT."""
    if cache_path.exists():
        df = pd.read_csv(cache_path)
        print(f"  Loaded {len(df)} polygon coords from cache")
        return df

    poly_ids = df_mukeys["poly_id"].astype(int).tolist()
    n_batches = (len(poly_ids) + BATCH - 1) // BATCH
    print(f"  Fetching polygon coords ({len(poly_ids)} polys in {n_batches} batches)...")

    records = []
    for i in range(n_batches):
        batch = poly_ids[i*BATCH:(i+1)*BATCH]
        ids_str = ",".join(str(p) for p in batch)
        q = f"SELECT * FROM mupolygon WHERE mupolygonkey IN ({ids_str})"
        try:
            rows = sdm_query(q, timeout=60)
        except Exception as e:
            print(f"\n    Batch {i+1}/{n_batches} failed: {e}")
            time.sleep(2)
            continue

        for row in rows:
            # col4=mukey, col6=WKT geographic (lon lat)
            mukey = row[4]
            wkt   = row[6] if len(row) > 6 else ""
            m = re.search(r"([-\d.]+)\s+([-\d.]+)", wkt)
            if not m:
                continue
            lon, lat = float(m.group(1)), float(m.group(2))
            records.append({"mukey": mukey, "lon": lon, "lat": lat})

        print(f"    Batch {i+1}/{n_batches}: {len(rows)} rows (total: {len(records)})", end="\r")
        time.sleep(0.05)

    print()
    df = pd.DataFrame(records)
    df.to_csv(cache_path, index=False)
    print(f"  Cached {len(df)} poly coords to {cache_path.name}")
    return df


# ── IDW ────────────────────────────────────────────────────────────────────────

def idw_k(src_pts, src_vals, tgt_pts, k=8, power=2):
    k = min(k, len(src_pts))
    tree = cKDTree(src_pts)
    dists, idxs = tree.query(tgt_pts, k=k)
    if k == 1:
        dists = dists[:, np.newaxis]
        idxs  = idxs[:, np.newaxis]
    exact = dists[:, 0] == 0
    weights = 1.0 / np.where(dists == 0, 1e-10, dists) ** power
    weights /= weights.sum(axis=1, keepdims=True)
    interp = (weights * src_vals[idxs]).sum(axis=1)
    interp[exact] = src_vals[idxs[exact, 0]]
    return interp


# ── Plot ───────────────────────────────────────────────────────────────────────

def plot_soil(cfg, state, grid, processed):
    fig, ax = plt.subplots(figsize=(12, 10), facecolor=DARK_BG)
    ax.set_facecolor(DARK_BG)
    state.to_crs(cfg["utm_epsg"]).boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0)
    grid.to_crs(cfg["utm_epsg"]).plot(
        column="soil_score", ax=ax, cmap="RdYlGn",
        vmin=0, vmax=1, legend=True,
        legend_kwds={"shrink": 0.65, "label": "0=Group A (high perm) / 1=Group D (low perm)"},
        alpha=0.85,
    )
    ax.set_title(
        f"{cfg['name']}: Soil Permeability Score (SSURGO Hydrologic Group)\n"
        "(High = low-permeability soil = low surface-spill infiltration risk)",
        color=WHITE, fontsize=16, pad=10,
    )
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    out = processed / "soil_permeability.png"
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved {out.name}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("state")
    args = parser.parse_args()

    cfg = get_state(args.state)
    root, raw, processed, grid_path = get_paths(cfg["abbr"])
    cache_mukey = raw / "soil_mukeys.csv"
    cache_coords = raw / "soil_coords.csv"
    print(f"\n=== 09_soil: {cfg['name']} ({cfg['abbr']}) ===")

    grid  = gpd.read_file(grid_path)
    state = gpd.read_file(raw / "state.geojson")
    print(f"Grid: {len(grid)} cells")

    # Step 1: mukey → hydgrpdcd + poly_id
    df_mukeys = fetch_mukey_hydgrp(cfg["abbr"], cache_mukey)

    # Step 2: poly_id → first lon/lat
    df_coords = fetch_poly_coords(df_mukeys, cache_coords)

    # Merge and score
    df = df_mukeys.merge(df_coords, on="mukey", how="inner")
    df["score"] = df["hydgrpdcd"].map(HYDGRP_SCORE).fillna(0.5)
    # Average score for mukeys that appear multiple times
    df = df.groupby("mukey").agg(score=("score", "mean"), lon=("lon", "mean"), lat=("lat", "mean")).reset_index()

    print(f"  {len(df)} mukeys with location + score")
    print(f"  Hydgrpdcd distribution:\n{df_mukeys.hydgrpdcd.value_counts().to_string()}")

    if len(df) == 0:
        print("  No soil data — soil_score set to 0.5 (neutral)")
        grid["soil_score"] = 0.5
        grid.to_file(grid_path, driver="GeoJSON")
        return

    # IDW to grid centroids
    print("  IDW interpolation to grid centroids...")
    centroids = grid.geometry.centroid
    tgt_pts = np.column_stack([centroids.x, centroids.y])
    src_pts = df[["lon", "lat"]].values
    src_vals = df["score"].values

    soil_interp = idw_k(src_pts, src_vals, tgt_pts, k=IDW_K, power=IDW_POWER)
    grid["soil_score"] = np.clip(soil_interp, 0, 1).round(4)
    print(f"  soil_score range: {grid.soil_score.min():.3f} - {grid.soil_score.max():.3f}")
    print(f"  mean: {grid.soil_score.mean():.3f}")

    grid.to_file(grid_path, driver="GeoJSON")
    print(f"\nSaved grid to {grid_path.name}")

    plot_soil(cfg, state, grid, processed)
    print("Done.")


if __name__ == "__main__":
    main()
