"""
03_risk.py — Compute seismic and flood risk scores.

Adds to grid_scores.geojson:
  seismic_score — 1 - normalized PGA @ 2% in 50yr (USGS ASCE 7-22)
  flood_score   — 1.0 if outside SFHA, 0.0 if inside (FEMA NFHL)

Usage:
  python 03_risk.py WA
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
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).parent))
from config import get_state, get_paths

warnings.filterwarnings("ignore")
CRS = "EPSG:4326"
DARK_BG = "#1a1a2e"
WHITE = "white"


def fetch_seismic(state_gdf, raw):
    path = raw / "seismic_sample.csv"
    if path.exists():
        return pd.read_csv(path)
    bounds = state_gdf.total_bounds
    state_union = state_gdf.geometry.unary_union
    sample_lats = np.linspace(bounds[1] + 0.4, bounds[3] - 0.2, 6)
    sample_lons = np.linspace(bounds[0] + 0.4, bounds[2] - 0.2, 10)
    api_url = "https://earthquake.usgs.gov/ws/designmaps/asce7-22.json"
    records = []
    for lat in sample_lats:
        for lon in sample_lons:
            if not state_union.contains(Point(lon, lat)):
                continue
            try:
                r = requests.get(api_url, params={
                    "latitude": round(lat, 2), "longitude": round(lon, 2),
                    "riskCategory": "II", "siteClass": "C", "title": "datacenter-siting",
                }, headers={"User-Agent": "datacenter-siting-research/1.0"}, timeout=30)
                r.raise_for_status()
                pgam = r.json().get("response", {}).get("data", {}).get("pgam")
                if pgam is not None:
                    records.append({"lat": lat, "lon": lon, "pgam": float(pgam)})
                    print(f"  ({lat:.2f},{lon:.2f}) PGAM={pgam:.3f}g")
                time.sleep(0.3)
            except Exception as e:
                print(f"  Skipped ({lat:.2f},{lon:.2f}): {e}")
    df = pd.DataFrame(records)
    df.to_csv(path, index=False)
    print(f"  Saved {len(df)} seismic samples")
    return df


def fetch_flood(state_gdf, raw):
    path = raw / "sfha.geojson"
    if path.exists():
        return gpd.read_file(path)
    nfhl_url = ("https://hazards.fema.gov/arcgis/rest/services/"
                "public/NFHL/MapServer/28/query")
    bounds = state_gdf.total_bounds
    lon_edges = np.linspace(bounds[0], bounds[2], 9)
    lat_edges = np.linspace(bounds[1], bounds[3], 6)
    all_features = []
    for i in range(len(lat_edges) - 1):
        for j in range(len(lon_edges) - 1):
            bbox = f"{lon_edges[j]},{lat_edges[i]},{lon_edges[j+1]},{lat_edges[i+1]}"
            try:
                r = requests.get(nfhl_url, params={
                    "geometry": bbox, "geometryType": "esriGeometryEnvelope",
                    "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
                    "where": "FLD_ZONE IN ('A','AE','AH','AO','AR','A99','VE','V')",
                    "outFields": "FLD_ZONE", "returnGeometry": "true",
                    "outSR": "4326", "resultRecordCount": "1000", "f": "geojson",
                }, headers={"User-Agent": "datacenter-siting-research/1.0"}, timeout=60)
                r.raise_for_status()
                feats = r.json().get("features", [])
                all_features.extend(feats)
                print(f"  Tile {i},{j}: {len(feats)} SFHA features")
                time.sleep(0.2)
            except Exception as e:
                print(f"  Tile {i},{j} skipped: {e}")
    if all_features:
        sfha = gpd.GeoDataFrame.from_features(all_features, crs=CRS)
        sfha = sfha[sfha.geometry.is_valid].dissolve().reset_index(drop=True)
        sfha.to_file(path, driver="GeoJSON")
        print(f"  Saved {len(sfha)} SFHA polygon(s)")
        return sfha
    print("  WARNING: No SFHA features returned; flood_score defaults to 1.0")
    return None


def idw_k(src_pts, src_vals, tgt_pts, k=8, power=2):
    tree = cKDTree(src_pts)
    dists, idxs = tree.query(tgt_pts, k=min(k, len(src_pts)))
    dists = np.where(dists < 1e-6, 1e-6, dists)
    weights = 1.0 / dists ** power
    weights /= weights.sum(axis=1, keepdims=True)
    return (weights * src_vals[idxs]).sum(axis=1)


def plot_risk(cfg, state, dc_gdf, grid, processed):
    layers = [
        ("seismic_score", "Seismic Safety", "(1 = lowest PGA)"),
        ("flood_score",   "Flood Safety",   "(1 = outside SFHA)"),
    ]
    plt.rcParams.update({"text.color": WHITE, "axes.labelcolor": WHITE,
                         "xtick.color": WHITE, "ytick.color": WHITE, "font.size": 16})
    fig, axes = plt.subplots(1, 2, figsize=(20, 9), facecolor=DARK_BG)
    for ax, (col, title, sub) in zip(axes, layers):
        ax.set_facecolor(DARK_BG)
        state.boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0, zorder=1)
        n0 = len(fig.axes)
        grid.plot(column=col, ax=ax, cmap="RdYlGn", vmin=0, vmax=1,
                  legend=True, legend_kwds={"shrink": 0.65, "label": "0=poor / 1=ideal"},
                  alpha=0.85, zorder=2)
        if len(fig.axes) > n0:
            cb = fig.axes[-1]; cb.tick_params(labelsize=14, colors=WHITE)
            cb.yaxis.label.set_color(WHITE)
        if len(dc_gdf) > 0:
            rep = dc_gdf[dc_gdf["source"].isin(["reported", "OSM"])]
            prop = dc_gdf[dc_gdf["source"] == "proposed"]
            ax.scatter(rep.geometry.x, rep.geometry.y, c=WHITE, s=100, marker="D",
                       zorder=5, edgecolors="black", linewidths=0.8)
            ax.scatter(prop.geometry.x, prop.geometry.y, facecolors="none", s=100,
                       marker="D", zorder=5, edgecolors="black", linewidths=1.5)
        ax.set_title(f"{title}\n{sub}", color=WHITE, fontsize=20, pad=10, linespacing=1.4)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        for s in ax.spines.values():
            s.set_edgecolor("#4a4a6a")
    plt.suptitle(f"{cfg['name']}: Risk Modifiers", color=WHITE, fontsize=22, y=0.90)
    plt.tight_layout(rect=[0, 0, 1, 0.86])
    out = processed / "risk_modifiers.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved {out.name}")


def main():
    parser = argparse.ArgumentParser(description="Compute seismic and flood risk scores.")
    parser.add_argument("state", help="Two-letter state abbreviation (e.g. WA)")
    args = parser.parse_args()

    cfg = get_state(args.state)
    root, raw, processed, grid_path = get_paths(cfg["abbr"])
    crs_proj = cfg["utm_epsg"]
    print(f"\n=== 03_risk: {cfg['name']} ({cfg['abbr']}) ===")

    state = gpd.read_file(raw / "state.geojson")
    dc_gdf = gpd.read_file(raw / "datacenters.geojson") if (raw / "datacenters.geojson").exists() else \
             gpd.GeoDataFrame(columns=["source", "geometry"], crs=CRS)
    grid = gpd.read_file(grid_path)
    print(f"Grid: {len(grid)} cells")

    print("Seismic hazard (seismic_score)...")
    seismic_df = fetch_seismic(state, raw)
    centroids = grid.geometry.centroid
    tgt = np.column_stack([[p.y for p in centroids], [p.x for p in centroids]])
    src = seismic_df[["lat", "lon"]].values
    pgam_interp = idw_k(src, seismic_df["pgam"].values, tgt)
    pmax = np.percentile(pgam_interp, 99)
    grid["seismic_score"] = 1.0 - (pgam_interp / pmax).clip(0, 1)
    print(f"  seismic_score: {grid['seismic_score'].min():.3f} - {grid['seismic_score'].max():.3f}")

    print("Flood zones (flood_score)...")
    sfha = fetch_flood(state, raw)
    if sfha is not None and len(sfha) > 0:
        sfha_union = sfha.geometry.buffer(0).unary_union
        grid["flood_score"] = grid.geometry.centroid.apply(
            lambda pt: 0.0 if sfha_union.contains(pt) else 1.0
        )
    else:
        grid["flood_score"] = 1.0
    n_flooded = (grid["flood_score"] == 0.0).sum()
    print(f"  flood_score: {n_flooded} cells in SFHA (score=0.0)")

    grid.to_file(grid_path, driver="GeoJSON")
    print(f"\nSaved grid to {grid_path.name}")

    print("Risk map...")
    plot_risk(cfg, state, dc_gdf, grid, processed)
    print("Done.")


if __name__ == "__main__":
    main()
