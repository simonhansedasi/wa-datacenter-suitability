"""
04_environment.py — Compute contamination and waterway sensitivity scores.

Adds to grid_scores.geojson:
  contamination_score — normalized distance to nearest EPA TRI industrial facility
                        (1 = far from sites / low contamination risk)
  waterway_score      — normalized distance to nearest major river
                        (1 = far from regulated waterways)

TRI data: EPA Toxics Release Inventory REST API (state-filtered, auto-downloaded)
Waterways: OSM Overpass (waterway=river, for state bbox)

Usage:
  python 04_environment.py WA
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
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).parent))
from config import get_state, get_paths

warnings.filterwarnings("ignore")
CRS = "EPSG:4326"
DARK_BG = "#1a1a2e"
WHITE = "white"


def fetch_tri_facilities(abbr, raw):
    """Download EPA TRI industrial facilities for the state via Envirofacts REST API."""
    path = raw / "tri_facilities.csv"
    if path.exists():
        df = pd.read_csv(path)
        if len(df) > 0:
            return df
    url = f"https://data.epa.gov/efservice/TRI_FACILITY/STATE_ABBR/{abbr}/JSON"
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": "datacenter-siting-research/1.0"})
        r.raise_for_status()
        data = r.json()
        if data and isinstance(data, list):
            df = pd.DataFrame(data)
            df["lat"] = pd.to_numeric(df.get("pref_latitude"), errors="coerce")
            # TRI stores longitude as positive — negate to get West-hemisphere coords
            df["lon"] = -pd.to_numeric(df.get("pref_longitude"), errors="coerce")
            df["name"] = df.get("facility_name", "")
            df = df[["lat", "lon", "name"]].dropna(subset=["lat", "lon"])
            if len(df) > 0:
                df.to_csv(path, index=False)
                print(f"  TRI API: {len(df)} facilities for {abbr}")
                return df
    except Exception as e:
        print(f"  TRI API failed: {e}")

    print(f"  WARNING: No TRI data for {abbr}; contamination_score will be uniform 1.0")
    df = pd.DataFrame(columns=["lat", "lon", "name"])
    df.to_csv(path, index=False)
    return df


def fetch_osm_rivers(bbox, raw):
    """Fetch major rivers (waterway=river) from OSM for the state bbox."""
    path = raw / "rivers.geojson"
    if path.exists():
        return gpd.read_file(path)
    west, south, east, north = bbox
    query = f"""
[out:json][timeout:90];
(
  way["waterway"="river"]({south},{west},{north},{east});
);
out geom;
"""
    try:
        r = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            headers={"User-Agent": "datacenter-siting-research/1.0"},
            timeout=120,
        )
        r.raise_for_status()
        lines = []
        for el in r.json().get("elements", []):
            if el.get("type") == "way" and "geometry" in el:
                coords = [(n["lon"], n["lat"]) for n in el["geometry"]]
                if len(coords) >= 2:
                    lines.append({
                        "name": el.get("tags", {}).get("name", ""),
                        "geometry": LineString(coords),
                    })
        if lines:
            gdf = gpd.GeoDataFrame(lines, crs=CRS)
            gdf.to_file(path, driver="GeoJSON")
            print(f"  OSM: {len(gdf)} river segments")
            return gdf
    except Exception as e:
        print(f"  OSM rivers failed: {e}")
    gdf = gpd.GeoDataFrame(columns=["name", "geometry"], crs=CRS)
    gdf.to_file(path, driver="GeoJSON")
    return gdf


def plot_environment(cfg, state, dc_gdf, grid, processed):
    layers = [
        ("contamination_score", "Contamination Proximity", "(1 = far from Superfund NPL site)"),
        ("waterway_score",      "Waterway Sensitivity",    "(1 = far from major river)"),
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
    plt.suptitle(f"{cfg['name']}: Environmental Risk", color=WHITE, fontsize=22, y=0.90)
    plt.tight_layout(rect=[0, 0, 1, 0.86])
    out = processed / "environmental_risk.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved {out.name}")


def main():
    parser = argparse.ArgumentParser(description="Compute contamination and waterway scores.")
    parser.add_argument("state", help="Two-letter state abbreviation (e.g. WA)")
    args = parser.parse_args()

    cfg = get_state(args.state)
    root, raw, processed, grid_path = get_paths(cfg["abbr"])
    crs_proj = cfg["utm_epsg"]
    print(f"\n=== 04_environment: {cfg['name']} ({cfg['abbr']}) ===")

    state = gpd.read_file(raw / "state.geojson")
    dc_gdf = gpd.read_file(raw / "datacenters.geojson") if (raw / "datacenters.geojson").exists() else \
             gpd.GeoDataFrame(columns=["source", "geometry"], crs=CRS)
    grid = gpd.read_file(grid_path)
    grid_proj = grid.to_crs(crs_proj)
    centroids_proj = np.column_stack([
        [c.x for c in grid_proj.geometry.centroid],
        [c.y for c in grid_proj.geometry.centroid],
    ])
    print(f"Grid: {len(grid)} cells")

    print("EPA TRI industrial facilities (contamination_score)...")
    tri_df = fetch_tri_facilities(cfg["abbr"], raw)
    if len(tri_df) > 0:
        tri_gdf = gpd.GeoDataFrame(tri_df,
                                   geometry=gpd.points_from_xy(tri_df["lon"], tri_df["lat"]),
                                   crs=CRS).to_crs(crs_proj)
        tri_coords = np.column_stack([tri_gdf.geometry.x, tri_gdf.geometry.y])
        tree = cKDTree(tri_coords)
        dist, _ = tree.query(centroids_proj, k=1)
        grid["contamination_score"] = dist / dist.max()
    else:
        grid["contamination_score"] = 1.0
    print(f"  contamination_score: {grid['contamination_score'].min():.3f} - {grid['contamination_score'].max():.3f}")

    print("OSM major rivers (waterway_score)...")
    rivers = fetch_osm_rivers(cfg["bbox"], raw)
    if len(rivers) > 0:
        rivers_proj = rivers.to_crs(crs_proj)
        rivers_union = rivers_proj.geometry.unary_union
        dists_riv = np.array([rivers_union.distance(
            gpd.GeoSeries([pt], crs=crs_proj).iloc[0]
        ) for pt in grid_proj.geometry.centroid])
        grid["waterway_score"] = dists_riv / dists_riv.max()
    else:
        print("  No river data; waterway_score=1.0 (neutral)")
        grid["waterway_score"] = 1.0
    print(f"  waterway_score: {grid['waterway_score'].min():.3f} - {grid['waterway_score'].max():.3f}")

    grid.to_file(grid_path, driver="GeoJSON")
    print(f"\nSaved grid to {grid_path.name}")

    print("Environment map...")
    plot_environment(cfg, state, dc_gdf, grid, processed)
    print("Done.")


if __name__ == "__main__":
    main()
