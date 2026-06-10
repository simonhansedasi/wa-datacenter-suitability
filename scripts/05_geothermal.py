"""
05_geothermal.py — Compute geothermal opportunity score.

Adds to grid_scores.geojson:
  geothermal_score — normalized heat flow (1 = highest), IDW from IHFC GHFDB 2024

Data source: IHFC_2024_GHFDB.shp in data/raw/ (global shapefile, filtered to state bbox)
If the global shapefile is absent, falls back to data/{STATE}/raw/heatflow.csv if present.

Usage:
  python 05_geothermal.py WA
"""

import argparse
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from config import get_state, get_paths, PROJECT_ROOT

warnings.filterwarnings("ignore")
CRS = "EPSG:4326"
DARK_BG = "#1a1a2e"
WHITE = "white"

IHFC_GLOBAL = PROJECT_ROOT / "data" / "raw" / "IHFC_2024_GHFDB.shp"


def load_heatflow(abbr, bbox, raw):
    """Load heat flow data filtered to state bbox, using cache if available."""
    cache = raw / "heatflow.csv"
    if cache.exists():
        df = pd.read_csv(cache)
        if len(df) > 0:
            print(f"  Loaded {len(df)} boreholes from cache")
            return df

    west, south, east, north = bbox

    # Try global IHFC shapefile first
    if IHFC_GLOBAL.exists():
        print(f"  Reading IHFC_2024_GHFDB.shp and filtering to {abbr} bbox...")
        gdf = gpd.read_file(IHFC_GLOBAL)
        # Geometry is Point; extract lat/lon from geometry
        gdf["lon"] = gdf.geometry.x
        gdf["lat"] = gdf.geometry.y
        mask = (
            (gdf["lon"] >= west) & (gdf["lon"] <= east) &
            (gdf["lat"] >= south) & (gdf["lat"] <= north)
        )
        subset = gdf.loc[mask, ["q", "lat", "lon"]].copy()
        subset = subset.dropna(subset=["q", "lat", "lon"])
        subset["q"] = pd.to_numeric(subset["q"], errors="coerce")
        subset = subset.dropna(subset=["q"])
        subset = subset[subset["q"] > 0]
        df = subset.reset_index(drop=True)
        df.to_csv(cache, index=False)
        print(f"  {len(df)} boreholes in {abbr} bbox; cached to {cache.name}")
        return df

    print(f"  WARNING: IHFC_2024_GHFDB.shp not found at {IHFC_GLOBAL}")
    print(f"  Place the IHFC 2024 shapefile at: {IHFC_GLOBAL}")
    print(f"  geothermal_score will be uniform 0.5 (neutral)")
    return pd.DataFrame(columns=["q", "lat", "lon"])


def idw_k(src_pts, src_vals, tgt_pts, k=8, power=2):
    k = min(k, len(src_pts))
    tree = cKDTree(src_pts)
    dists, idxs = tree.query(tgt_pts, k=k)
    if k == 1:
        dists = dists[:, np.newaxis]
        idxs = idxs[:, np.newaxis]
    dists = np.where(dists < 1e-6, 1e-6, dists)
    weights = 1.0 / dists ** power
    weights /= weights.sum(axis=1, keepdims=True)
    return (weights * src_vals[idxs]).sum(axis=1)


def plot_geothermal(cfg, state, dc_gdf, hf_df, grid, processed):
    plt.rcParams.update({"text.color": WHITE, "axes.labelcolor": WHITE,
                         "xtick.color": WHITE, "ytick.color": WHITE, "font.size": 16})
    fig, ax = plt.subplots(1, 1, figsize=(12, 10), facecolor=DARK_BG)
    ax.set_facecolor(DARK_BG)
    state.boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0, zorder=1)
    n0 = len(fig.axes)
    grid.plot(column="geothermal_score", ax=ax, cmap="inferno", vmin=0, vmax=1,
              legend=True, legend_kwds={"shrink": 0.65, "label": "0=low / 1=high heat flow"},
              alpha=0.85, zorder=2)
    if len(fig.axes) > n0:
        cb = fig.axes[-1]; cb.tick_params(labelsize=14, colors=WHITE)
        cb.yaxis.label.set_color(WHITE)
    if len(hf_df) > 0:
        ax.scatter(hf_df["lon"], hf_df["lat"], c=hf_df["q"].clip(upper=hf_df["q"].quantile(0.95)),
                   cmap="inferno", s=8, alpha=0.4, zorder=3, linewidths=0)
    if len(dc_gdf) > 0:
        rep = dc_gdf[dc_gdf["source"].isin(["reported", "OSM"])]
        prop = dc_gdf[dc_gdf["source"] == "proposed"]
        ax.scatter(rep.geometry.x, rep.geometry.y, c=WHITE, s=100, marker="D",
                   zorder=5, edgecolors="black", linewidths=0.8)
        ax.scatter(prop.geometry.x, prop.geometry.y, facecolors="none", s=100,
                   marker="D", zorder=5, edgecolors="black", linewidths=1.5)
    ax.set_title(
        f"{cfg['name']}: Geothermal Heat Flow (IHFC GHFDB 2024)\n"
        f"(IDW; {len(hf_df)} boreholes; capped at 95th pct)\n"
        "White filled = existing DC  /  outline = proposed DC",
        color=WHITE, fontsize=18, pad=10, linespacing=1.4,
    )
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for s in ax.spines.values():
        s.set_edgecolor("#4a4a6a")
    plt.tight_layout()
    out = processed / "geothermal.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved {out.name}")


def main():
    parser = argparse.ArgumentParser(description="Compute geothermal opportunity score.")
    parser.add_argument("state", help="Two-letter state abbreviation (e.g. WA)")
    args = parser.parse_args()

    cfg = get_state(args.state)
    root, raw, processed, grid_path = get_paths(cfg["abbr"])
    crs_proj = cfg["utm_epsg"]
    print(f"\n=== 05_geothermal: {cfg['name']} ({cfg['abbr']}) ===")

    state = gpd.read_file(raw / "state.geojson")
    dc_gdf = gpd.read_file(raw / "datacenters.geojson") if (raw / "datacenters.geojson").exists() else \
             gpd.GeoDataFrame(columns=["source", "geometry"], crs=CRS)
    grid = gpd.read_file(grid_path)
    print(f"Grid: {len(grid)} cells")

    hf_df = load_heatflow(cfg["abbr"], cfg["bbox"], raw)

    if len(hf_df) < 2:
        grid["geothermal_score"] = 0.5
        print("  Not enough borehole data; geothermal_score=0.5")
    else:
        q95 = np.percentile(hf_df["q"], 95)
        hf_df["q_capped"] = hf_df["q"].clip(upper=q95)

        grid_proj = grid.to_crs(crs_proj)
        hf_gdf = gpd.GeoDataFrame(hf_df, geometry=gpd.points_from_xy(hf_df["lon"], hf_df["lat"]),
                                   crs=CRS).to_crs(crs_proj)
        src_pts = np.column_stack([hf_gdf.geometry.x, hf_gdf.geometry.y])
        tgt_pts = np.column_stack([
            [c.x for c in grid_proj.geometry.centroid],
            [c.y for c in grid_proj.geometry.centroid],
        ])
        q_interp = idw_k(src_pts, hf_df["q_capped"].values, tgt_pts)
        grid["geothermal_score"] = q_interp / q_interp.max()
        print(f"  geothermal_score: {grid['geothermal_score'].min():.3f} - {grid['geothermal_score'].max():.3f}")

    grid.to_file(grid_path, driver="GeoJSON")
    print(f"\nSaved grid to {grid_path.name}")

    print("Geothermal map...")
    plot_geothermal(cfg, state, dc_gdf, hf_df, grid, processed)
    print("Done.")


if __name__ == "__main__":
    main()
