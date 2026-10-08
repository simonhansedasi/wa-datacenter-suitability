"""
08_aquifer.py — Compute groundwater depth score from USGS NWIS field measurements.

Adds to grid_scores.geojson:
  aquifer_score — normalized depth-to-water-table (1 = deepest = lowest contamination risk)

Method:
  - Fetches discrete depth-to-water measurements (parameter 72019, ft below land surface)
    from USGS Water Data API (field-measurements collection, new post-2025 API)
  - Computes median depth per monitoring site
  - IDW interpolation from well sites to grid cell centroids
  - Normalizes: p95 cap → 0-1 (high score = deep water table = low aquifer sensitivity)

Rationale: deep water table reduces risk of surface-spill groundwater contamination;
sites above shallow aquifers carry higher environmental risk for data center siting.

Usage:
  python 08_aquifer.py WA
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from config import get_state, get_paths

warnings.filterwarnings("ignore")
CRS = "EPSG:4326"
DARK_BG = "#1a1a2e"
WHITE = "white"

API_BASE = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/items"
PARAM_CODE = "72019"   # depth to water level, ft below land surface
PAGE_SIZE  = 5000
IDW_K      = 8
IDW_POWER  = 2


# ── Fetch ──────────────────────────────────────────────────────────────────────

def fetch_well_depths(bbox, cache_path):
    import requests

    if cache_path.exists():
        df = pd.read_csv(cache_path)
        print(f"  Loaded {len(df)} well measurements from cache")
        return df

    west, south, east, north = bbox
    bbox_str = f"{west},{south},{east},{north}"
    records = []
    offset = 0
    page = 0

    print(f"  Fetching NWIS depth-to-water (parameter {PARAM_CODE}) for bbox {bbox_str}...")
    while True:
        params = {
            "bbox": bbox_str,
            "parameter_code": PARAM_CODE,
            "limit": PAGE_SIZE,
            "offset": offset,
            "f": "json",
        }
        r = requests.get(API_BASE, params=params, timeout=60)
        if r.status_code == 400:
            # API caps total offset — stop pagination, use what we have
            print(f"\n  API offset limit reached at page {page+1}; using {len(records)} records")
            break
        r.raise_for_status()
        data = r.json()
        feats = data.get("features", [])
        for ft in feats:
            p = ft["properties"]
            geom = ft.get("geometry")
            if not geom or geom["type"] != "Point":
                continue
            try:
                depth = float(p["value"])
            except (TypeError, ValueError):
                continue
            if depth < 0:   # negative = water above land surface, skip
                continue
            records.append({
                "site_id": p["monitoring_location_id"],
                "lon": geom["coordinates"][0],
                "lat": geom["coordinates"][1],
                "depth_ft": depth,
            })
        page += 1
        print(f"    Page {page}: {len(feats)} records (total so far: {len(records)})", end="\r")
        if len(feats) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.1)

    print(f"\n  Downloaded {len(records)} depth measurements")
    df = pd.DataFrame(records)
    df.to_csv(cache_path, index=False)
    print(f"  Cached to {cache_path.name}")
    return df


def median_per_site(df):
    """Collapse multiple measurements per well to median depth."""
    med = (df.groupby("site_id")
             .agg(depth_ft=("depth_ft", "median"),
                  lat=("lat", "first"),
                  lon=("lon", "first"),
                  n_meas=("depth_ft", "count"))
             .reset_index())
    # Require at least 2 measurements for a stable median
    med = med[med["n_meas"] >= 2].reset_index(drop=True)
    print(f"  {len(med)} sites with >= 2 measurements (median depth: {med.depth_ft.median():.1f} ft)")
    return med


# ── IDW ────────────────────────────────────────────────────────────────────────

def idw_k(src_pts, src_vals, tgt_pts, k=8, power=2):
    k = min(k, len(src_pts))
    tree = cKDTree(src_pts)
    dists, idxs = tree.query(tgt_pts, k=k)
    if k == 1:
        dists = dists[:, np.newaxis]
        idxs  = idxs[:, np.newaxis]
    # Exact hit: distance = 0
    exact = (dists[:, 0] == 0)
    weights = 1.0 / np.where(dists == 0, 1e-10, dists) ** power
    weights /= weights.sum(axis=1, keepdims=True)
    interp = (weights * src_vals[idxs]).sum(axis=1)
    interp[exact] = src_vals[idxs[exact, 0]]
    return interp


# ── Plot ───────────────────────────────────────────────────────────────────────

def plot_aquifer(cfg, state, grid, processed):
    fig, ax = plt.subplots(figsize=(12, 10), facecolor=DARK_BG)
    ax.set_facecolor(DARK_BG)
    state.to_crs(cfg["utm_epsg"]).boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0)
    grid.to_crs(cfg["utm_epsg"]).plot(
        column="aquifer_score", ax=ax, cmap="YlOrRd_r",
        vmin=0, vmax=1, legend=True,
        legend_kwds={"shrink": 0.65, "label": "0=shallow water table / 1=deep"},
        alpha=0.85,
    )
    ax.set_title(
        f"{cfg['name']}: Depth-to-Water Score (USGS NWIS)\n"
        "(High = deep water table = lower aquifer contamination risk)",
        color=WHITE, fontsize=16, pad=10,
    )
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    out = processed / "aquifer_depth.png"
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
    cache = raw / "well_depths.csv"
    print(f"\n=== 08_aquifer: {cfg['name']} ({cfg['abbr']}) ===")

    grid = gpd.read_file(grid_path)
    state = gpd.read_file(raw / "state.geojson")
    print(f"Grid: {len(grid)} cells")

    # Fetch
    df_raw = fetch_well_depths(cfg["bbox"], cache)
    if len(df_raw) == 0:
        print("  No well data found — aquifer_score set to 0.5 (neutral)")
        grid["aquifer_score"] = 0.5
        grid.to_file(grid_path, driver="GeoJSON")
        return

    # Median per site
    sites = median_per_site(df_raw)

    # IDW to cell centroids
    print("  IDW interpolation to grid centroids...")
    centroids = grid.geometry.centroid
    tgt_pts = np.column_stack([centroids.x, centroids.y])
    src_pts = sites[["lon", "lat"]].values
    src_vals = sites["depth_ft"].values

    interp_depth = idw_k(src_pts, src_vals, tgt_pts, k=IDW_K, power=IDW_POWER)

    # Normalize: p95 cap → 0-1 (deeper = higher score)
    p95 = np.percentile(interp_depth, 95)
    grid["aquifer_score"] = np.clip(interp_depth / p95, 0, 1).round(4)
    print(f"  Depth range (interpolated): {interp_depth.min():.1f} - {interp_depth.max():.1f} ft")
    print(f"  p95 = {p95:.1f} ft  |  score range: {grid.aquifer_score.min():.3f} - {grid.aquifer_score.max():.3f}")

    grid.to_file(grid_path, driver="GeoJSON")
    print(f"\nSaved grid to {grid_path.name}")

    plot_aquifer(cfg, state, grid, processed)
    print("Done.")


if __name__ == "__main__":
    main()
