"""
10_soilprofile.py — Full-column soil profile scorer for contamination pathway risk.

Adds to grid_scores.geojson:
  soil_profile_score — 0-1 (high = low contamination pathway risk)

Method:
  - Queries SSURGO SDA chorizon table for all horizons 0-150cm:
      caco3_r   — lime/CaCO3 content (%)
      ksat_r    — hydraulic conductivity (µm/s)
      claytotal_r — clay content (%)
  - Per map unit: thickness-weighted mean K-sat and clay; MAX CaCO3 across horizons
  - Three sub-scores:
      caco3_score = 1 - min(max_caco3 / 15.0, 1)       high lime = high risk
      ksat_score  = 1 - clip(log1p(wmean_ksat) / log1p(100), 0, 1)  fast recharge = high risk
      clay_score  = clip(wmean_clay / 35.0, 0, 1)       deep clay = aquitard = low risk
  - Composite: 0.40 * caco3 + 0.35 * ksat + 0.25 * clay
  - IDW interpolation (k=8, power=2) from mukey representative points to grid centroids
  - Reuses soil_coords.csv from 09_soil.py for representative polygon coordinates

Rationale: Tom's observation — soil column flags (lime, fast permeability, no clay barrier)
determine whether a datacenter spill reaches groundwater. High score = clean column.

Usage:
  conda activate GrapeExpectations
  python 10_soilprofile.py WA

  With ZCTA subdir:
  DC_SUBDIR=zcta conda run -n GrapeExpectations python scripts/10_soilprofile.py WA
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
import requests
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from config import get_state, get_paths

warnings.filterwarnings("ignore")
CRS     = "EPSG:4326"
DARK_BG = "#1a1a2e"
WHITE   = "white"

SDM_URL  = "https://SDMDataAccess.sc.egov.usda.gov/Tabular/SDMTabularService/post.rest"
SDM_HDR  = {"Content-Type": "application/json"}
IDW_K    = 8
IDW_POWER = 2

# Contamination pathway thresholds
CACO3_THRESHOLD = 15.0   # % — above this, lime mobilization risk is high
KSAT_REF        = 100.0  # µm/s — log-scale reference for "very fast" permeability
CLAY_SATURATION = 35.0   # % — above this, solid aquitard protection assumed

# Sub-score weights (must sum to 1.0)
W_CACO3 = 0.40
W_KSAT  = 0.35
W_CLAY  = 0.25


# ── SDM helpers ────────────────────────────────────────────────────────────────

def sdm_query(q, timeout=240):
    r = requests.post(SDM_URL, headers=SDM_HDR, json={"query": q, "FORMAT": "JSON"}, timeout=timeout)
    r.raise_for_status()
    return requests.models.Response.json(r).get("Table", [])


def fetch_chorizon(state_abbr, cache_path):
    """Query SSURGO chorizon for all horizons 0-150cm. Returns DataFrame with raw horizon rows."""
    if cache_path.exists():
        df = pd.read_csv(cache_path)
        print(f"  Loaded {len(df)} horizon rows from cache")
        return df

    abbr = state_abbr.upper()
    print(f"  Querying SDM chorizon (0-150cm) for {abbr}...")
    q = f"""SELECT ch.mukey, ch.hzdept_r, ch.hzdepb_r,
               ch.caco3_r, ch.ksat_r, ch.claytotal_r
        FROM chorizon ch
        INNER JOIN mapunit mu ON ch.mukey = mu.mukey
        INNER JOIN legend l ON mu.lkey = l.lkey
        WHERE l.areasymbol LIKE '{abbr}%'
          AND ch.hzdept_r IS NOT NULL
          AND ch.hzdepb_r IS NOT NULL
          AND ch.hzdept_r < 150
        ORDER BY ch.mukey, ch.hzdept_r"""

    rows = sdm_query(q, timeout=300)
    print(f"  Got {len(rows)} horizon rows")

    df = pd.DataFrame(rows, columns=["mukey", "hzdept_r", "hzdepb_r", "caco3_r", "ksat_r", "claytotal_r"])
    for col in ["hzdept_r", "hzdepb_r", "caco3_r", "ksat_r", "claytotal_r"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.to_csv(cache_path, index=False)
    print(f"  Cached to {cache_path.name}")
    return df


# ── Aggregation ────────────────────────────────────────────────────────────────

def aggregate_per_mukey(df):
    """Compute per-mukey contamination pathway indicators.

    Returns DataFrame with columns: mukey, max_caco3, wmean_ksat, wmean_clay.
    """
    # Clip bottom depth at 150cm so partial horizons aren't over-counted
    df = df.copy()
    df["hzdepb_r"] = np.minimum(df["hzdepb_r"], 150.0)
    df["thickness"] = (df["hzdepb_r"] - df["hzdept_r"]).clip(lower=0)

    # Drop horizons with zero thickness (degenerate entries)
    df = df[df["thickness"] > 0].copy()

    records = []
    for mukey, grp in df.groupby("mukey"):
        thick = grp["thickness"].values
        total = thick.sum()

        # CaCO3: MAX across horizons (flag if any horizon is lime-rich)
        max_caco3 = grp["caco3_r"].max()          # NaN if all missing
        if pd.isna(max_caco3):
            max_caco3 = 0.0                        # no lime detected = low risk

        # K-sat: thickness-weighted mean (NaN horizons excluded from weighting)
        ksat_valid = grp["ksat_r"].notna()
        if ksat_valid.any():
            kw = thick * grp["ksat_r"]
            tw = thick[ksat_valid.values].sum()
            wmean_ksat = kw[ksat_valid.values].sum() / tw if tw > 0 else np.nan
        else:
            wmean_ksat = np.nan

        # Clay: thickness-weighted mean
        clay_valid = grp["claytotal_r"].notna()
        if clay_valid.any():
            cw = thick * grp["claytotal_r"]
            tw = thick[clay_valid.values].sum()
            wmean_clay = cw[clay_valid.values].sum() / tw if tw > 0 else np.nan
        else:
            wmean_clay = np.nan

        records.append({
            "mukey":      str(mukey),
            "max_caco3":  max_caco3,
            "wmean_ksat": wmean_ksat,
            "wmean_clay": wmean_clay,
            "total_depth": total,
        })

    df_agg = pd.DataFrame(records)

    # Fill NaN with median (missing data = assume typical — not best, not worst)
    ksat_med = df_agg["wmean_ksat"].median()
    clay_med = df_agg["wmean_clay"].median()
    df_agg["wmean_ksat"] = df_agg["wmean_ksat"].fillna(ksat_med)
    df_agg["wmean_clay"] = df_agg["wmean_clay"].fillna(clay_med)
    print(f"  Aggregated {len(df_agg)} mukeys  |  "
          f"median K-sat={ksat_med:.2f} µm/s  clay={clay_med:.1f}%")
    return df_agg


def score_mukeys(df_agg):
    """Convert per-mukey indicators to a single 0-1 soil_profile_score."""
    # CaCO3 score: linear, 0% = perfect (1.0), 15%+ = worst (0.0)
    caco3_score = 1.0 - np.clip(df_agg["max_caco3"] / CACO3_THRESHOLD, 0, 1)

    # K-sat score: log-scale inverse — fast permeability = high risk = low score
    ksat_log = np.log1p(df_agg["wmean_ksat"].clip(lower=0))
    ksat_score = 1.0 - np.clip(ksat_log / np.log1p(KSAT_REF), 0, 1)

    # Clay score: linear aquitard proxy — more clay at depth = better barrier
    clay_score = np.clip(df_agg["wmean_clay"] / CLAY_SATURATION, 0, 1)

    df_agg = df_agg.copy()
    df_agg["caco3_score"] = caco3_score
    df_agg["ksat_score"]  = ksat_score
    df_agg["clay_score"]  = clay_score
    df_agg["soil_profile_score"] = (
        W_CACO3 * caco3_score +
        W_KSAT  * ksat_score  +
        W_CLAY  * clay_score
    ).round(4)

    print(f"  Score range: {df_agg.soil_profile_score.min():.3f} - "
          f"{df_agg.soil_profile_score.max():.3f}  "
          f"(mean {df_agg.soil_profile_score.mean():.3f})")
    print(f"    caco3_score  mean={caco3_score.mean():.3f}  "
          f"ksat_score mean={ksat_score.mean():.3f}  "
          f"clay_score mean={clay_score.mean():.3f}")
    return df_agg


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

def plot_profile(cfg, state, grid, processed):
    fig, axes = plt.subplots(1, 2, figsize=(20, 8), facecolor=DARK_BG)

    panels = [
        ("soil_profile_score", "Composite Risk Score", "RdYlGn",
         "0=high contamination pathway risk / 1=clean column"),
    ]

    # Left: composite score
    ax = axes[0]
    ax.set_facecolor(DARK_BG)
    state.to_crs(cfg["utm_epsg"]).boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0)
    grid.to_crs(cfg["utm_epsg"]).plot(
        column="soil_profile_score", ax=ax, cmap="RdYlGn",
        vmin=0, vmax=1, legend=True,
        legend_kwds={"shrink": 0.65, "label": "0=high risk / 1=low risk"},
        alpha=0.85,
    )
    ax.set_title(f"{cfg['name']}: Soil Profile Score (composite)", color=WHITE, fontsize=14, pad=8)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    # Right: K-sat sub-score
    ax = axes[1]
    ax.set_facecolor(DARK_BG)
    if "ksat_score" in grid.columns:
        state.to_crs(cfg["utm_epsg"]).boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0)
        grid.to_crs(cfg["utm_epsg"]).plot(
            column="ksat_score", ax=ax, cmap="RdYlBu",
            vmin=0, vmax=1, legend=True,
            legend_kwds={"shrink": 0.65, "label": "0=fast permeability / 1=slow"},
            alpha=0.85,
        )
        ax.set_title(f"{cfg['name']}: K-sat Sub-score", color=WHITE, fontsize=14, pad=8)
    else:
        ax.text(0.5, 0.5, "K-sat sub-score\nnot available", ha="center", va="center",
                transform=ax.transAxes, color=WHITE, fontsize=12)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    fig.suptitle(
        "Soil Column Contamination Pathway Risk (SSURGO 0-150cm)\n"
        "CaCO3 (lime), K-sat (permeability), Clay (aquitard) — high score = low risk",
        color=WHITE, fontsize=13, y=1.01,
    )
    out = processed / "soil_profile.png"
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved {out.name}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("state")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    cfg = get_state(args.state)
    root, raw, processed, grid_path = get_paths(cfg["abbr"])
    cache_horizons = raw / "soil_profile_horizons.csv"
    cache_coords   = raw / "soil_coords.csv"

    print(f"\n=== 10_soilprofile: {cfg['name']} ({cfg['abbr']}) ===")

    grid  = gpd.read_file(grid_path)
    state = gpd.read_file(raw / "state.geojson")
    print(f"Grid: {len(grid)} cells")

    # Step 1: Fetch chorizon data
    df_horizons = fetch_chorizon(cfg["abbr"], cache_horizons)

    if len(df_horizons) == 0:
        print("  No chorizon data — soil_profile_score set to 0.5 (neutral)")
        grid["soil_profile_score"] = 0.5
        grid.to_file(grid_path, driver="GeoJSON")
        return

    # Step 2: Aggregate per mukey
    df_agg = aggregate_per_mukey(df_horizons)
    df_agg = score_mukeys(df_agg)

    # Step 3: Merge with representative polygon coordinates
    if not cache_coords.exists():
        print("  WARNING: soil_coords.csv not found — run 09_soil.py first")
        print("  soil_profile_score set to 0.5 (neutral)")
        grid["soil_profile_score"] = 0.5
        grid.to_file(grid_path, driver="GeoJSON")
        return

    df_coords = pd.read_csv(cache_coords, dtype={"mukey": str})
    df = df_agg.merge(df_coords, on="mukey", how="inner")
    print(f"  {len(df)} mukeys with score + location (of {len(df_agg)} scored)")

    if len(df) < 10:
        print("  Too few matched mukeys — check soil_coords.csv alignment")
        grid["soil_profile_score"] = 0.5
        grid.to_file(grid_path, driver="GeoJSON")
        return

    # Step 4: IDW to grid centroids
    print("  IDW interpolation to grid centroids...")
    centroids = grid.geometry.centroid
    tgt_pts  = np.column_stack([centroids.x, centroids.y])
    src_pts  = df[["lon", "lat"]].values
    src_vals = df["soil_profile_score"].values

    interp = idw_k(src_pts, src_vals, tgt_pts, k=IDW_K, power=IDW_POWER)
    grid["soil_profile_score"] = np.clip(interp, 0, 1).round(4)

    # Also IDW the K-sat sub-score for the plot
    ksat_interp = idw_k(src_pts, df["ksat_score"].values, tgt_pts, k=IDW_K, power=IDW_POWER)
    grid["ksat_score"] = np.clip(ksat_interp, 0, 1).round(4)

    print(f"  Final grid range: {grid.soil_profile_score.min():.3f} - "
          f"{grid.soil_profile_score.max():.3f}  "
          f"(mean {grid.soil_profile_score.mean():.3f})")

    grid.to_file(grid_path, driver="GeoJSON")
    print(f"\nSaved grid to {grid_path.name}")

    if not args.no_plot:
        plot_profile(cfg, state, grid, processed)

    print("Done.")


if __name__ == "__main__":
    main()
