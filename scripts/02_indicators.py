"""
02_indicators.py — Build fishnet grid and compute stress indicators.

Creates grid_scores.geojson with columns:
  cell_id            — integer fishnet cell index
  tx_score           — proximity to HV transmission (1 = adjacent)
  water_score        — 30-yr mean annual precipitation (1 = highest / least stressed)
  ej_score           — 1 - Census ACS demographic burden (1 = least burdened)
  pop_exposure_score — 1 - population density per km² (1 = fewest residents)

Base geography: 0.15° fishnet grid (~14 km at mid-latitudes). Uniform coverage across
the full state regardless of population density — intentional for physical suitability
scoring where every part of the state is a candidate.

Reads:  data/{STATE}/raw/state.geojson, transmission.geojson
Writes: data/{STATE}/grid_scores.geojson

Usage:
  python 02_indicators.py WA
  CENSUS_API_KEY=abc123 python 02_indicators.py WA
"""

import argparse
import io
import os
import sys
import time
import warnings
import zipfile
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, box

sys.path.insert(0, str(Path(__file__).parent))
from config import get_state, get_paths

warnings.filterwarnings("ignore")
CRS = "EPSG:4326"
DARK_BG = "#1a1a2e"
WHITE = "white"
CELL_SIZE = 0.15


def create_fishnet(state_gdf, cell_size=CELL_SIZE):
    """Create uniform grid clipped to state boundary."""
    minx, miny, maxx, maxy = state_gdf.total_bounds
    cols = np.arange(minx, maxx, cell_size)
    rows = np.arange(miny, maxy, cell_size)
    polygons = [box(x, y, x + cell_size, y + cell_size) for x in cols for y in rows]
    grid = gpd.GeoDataFrame({"geometry": polygons}, crs=CRS)
    state_union = state_gdf.geometry.unary_union
    grid = grid[grid.geometry.centroid.within(state_union)].reset_index(drop=True)
    grid["cell_id"] = grid.index
    return grid


def load_census_key():
    key = os.environ.get("CENSUS_API_KEY")
    if key:
        return key
    for env_file in [Path("/home/simonhans/coding/snotrac/.env"), Path.home() / ".env"]:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("CENSUS_API_KEY"):
                    return line.split("=", 1)[1].strip()
    raise RuntimeError(
        "Census API key not found. Set CENSUS_API_KEY env var or add to ~/.env"
    )


def fetch_tracts(state_fips, raw):
    """Download Census TIGER tract boundaries for the state."""
    path = raw / "tracts.geojson"
    if path.exists():
        return gpd.read_file(path)
    url = f"https://www2.census.gov/geo/tiger/TIGER2022/TRACT/tl_2022_{state_fips}_tract.zip"
    print(f"  Downloading tract boundaries for FIPS {state_fips}...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    shp_dir = raw / "tracts_shp"
    shp_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(shp_dir)
    tracts = gpd.read_file(shp_dir / f"tl_2022_{state_fips}_tract.shp").to_crs(CRS)
    tracts.to_file(path, driver="GeoJSON")
    print(f"  Saved {len(tracts)} tracts to {path.name}")
    return tracts


def fetch_acs(state_fips, raw):
    """Download ACS 5-year tract-level demographic data."""
    path = raw / "acs_demog.csv"
    if path.exists():
        df = pd.read_csv(path, dtype={"GEOID": str})
        if "pop" in df.columns and "GEOID" in df.columns:
            return df
        print("  Cache missing required columns; re-fetching ACS data...")
    key = load_census_key()
    params = {
        "get": "NAME,B17001_001E,B17001_002E,B02001_001E,B02001_002E,B01003_001E",
        "for": "tract:*",
        "in": f"state:{state_fips}",
        "key": key,
    }
    print(f"  Downloading ACS 5-year tract data for FIPS {state_fips}...")
    r = requests.get("https://api.census.gov/data/2022/acs/acs5", params=params, timeout=60)
    r.raise_for_status()
    rows = r.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    for col in ["B17001_001E", "B17001_002E", "B02001_001E", "B02001_002E", "B01003_001E"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["GEOID"] = (
        df["state"].str.zfill(2) + df["county"].str.zfill(3) + df["tract"].str.zfill(6)
    )
    df["poverty_rate"] = (df["B17001_002E"] / df["B17001_001E"]).clip(0, 1)
    df["minority_rate"] = (1 - df["B02001_002E"] / df["B02001_001E"]).clip(0, 1)
    df["demog_index"] = (df["poverty_rate"] + df["minority_rate"]) / 2
    df["pop"] = df["B01003_001E"]
    out = df[["GEOID", "poverty_rate", "minority_rate", "demog_index", "pop"]].copy()
    out.to_csv(path, index=False)
    print(f"  Saved {len(out)} tracts to {path.name}")
    return out


def fetch_precip(state_gdf, raw):
    path = raw / "precip_coarse.csv"
    if path.exists():
        return pd.read_csv(path)
    bounds = state_gdf.total_bounds
    state_union = state_gdf.geometry.unary_union
    sample_lats = np.linspace(bounds[1] + 0.4, bounds[3] - 0.2, 7)
    sample_lons = np.linspace(bounds[0] + 0.4, bounds[2] - 0.2, 11)
    records = []
    for lat in sample_lats:
        for lon in sample_lons:
            if not state_union.contains(Point(lon, lat)):
                continue
            try:
                params = {
                    "latitude": round(lat, 2), "longitude": round(lon, 2),
                    "start_date": "1991-01-01", "end_date": "2020-12-31",
                    "daily": "precipitation_sum", "timezone": "UTC",
                }
                r = requests.get("https://archive-api.open-meteo.com/v1/archive",
                                 params=params, timeout=30)
                r.raise_for_status()
                vals = [v for v in r.json()["daily"]["precipitation_sum"] if v is not None]
                records.append({"lat": lat, "lon": lon, "ann_precip_mm": sum(vals) / 30.0})
                time.sleep(0.05)
            except Exception as e:
                print(f"  Skipped ({lat:.2f},{lon:.2f}): {e}")
    df = pd.DataFrame(records)
    df.to_csv(path, index=False)
    print(f"  Saved {len(df)} precip points to {path.name}")
    return df


def idw(src_lats, src_lons, src_vals, tgt_lats, tgt_lons, power=2):
    results = []
    for lat, lon in zip(tgt_lats, tgt_lons):
        dists = np.sqrt((src_lats - lat) ** 2 + (src_lons - lon) ** 2)
        dists = np.maximum(dists, 1e-10)
        w = 1.0 / dists ** power
        results.append(float(np.sum(w * src_vals) / np.sum(w)))
    return results


def plot_indicators(cfg, state, dc_gdf, grid, processed):
    layers = [
        ("tx_score",           "Transmission Proximity",  "(1 = adjacent to HV line)"),
        ("water_score",        "Water Availability",       "(1 = highest precip)"),
        ("ej_score",           "Community Burden",         "(1 = lowest demographic burden)"),
        ("pop_exposure_score", "Population Exposure",      "(1 = fewest residents in vicinity)"),
    ]
    plt.rcParams.update({"text.color": WHITE, "axes.labelcolor": WHITE,
                         "xtick.color": WHITE, "ytick.color": WHITE, "font.size": 16})
    fig, axes = plt.subplots(1, 4, figsize=(32, 9), facecolor=DARK_BG)
    for ax, (col, title, subtitle) in zip(axes, layers):
        ax.set_facecolor(DARK_BG)
        state.boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0, zorder=1)
        n_before = len(fig.axes)
        grid.plot(column=col, ax=ax, cmap="RdYlGn", vmin=0, vmax=1,
                  legend=True, legend_kwds={"shrink": 0.65, "label": "0=poor / 1=ideal"},
                  alpha=0.85, zorder=2)
        if len(fig.axes) > n_before:
            cb = fig.axes[-1]
            cb.tick_params(labelsize=14, colors=WHITE)
            cb.yaxis.label.set_color(WHITE)
        if len(dc_gdf) > 0:
            rep = dc_gdf[dc_gdf["source"].isin(["reported", "OSM"])]
            prop = dc_gdf[dc_gdf["source"] == "proposed"]
            ax.scatter(rep.geometry.x, rep.geometry.y, c=WHITE, s=100, marker="D",
                       zorder=5, edgecolors="black", linewidths=0.8)
            ax.scatter(prop.geometry.x, prop.geometry.y, facecolors="none", s=100,
                       marker="D", zorder=5, edgecolors="black", linewidths=1.5)
        ax.set_title(f"{title}\n{subtitle}", color=WHITE, fontsize=20, pad=10, linespacing=1.4)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        for s in ax.spines.values():
            s.set_edgecolor("#4a4a6a")
    plt.suptitle(f"{cfg['name']}: Stress Indicators", color=WHITE, fontsize=22, y=0.90)
    plt.tight_layout(rect=[0, 0, 1, 0.86])
    out = processed / "indicators.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved {out.name}")


def main():
    parser = argparse.ArgumentParser(description="Build fishnet grid and compute stress indicators.")
    parser.add_argument("state", help="Two-letter state abbreviation (e.g. WA)")
    args = parser.parse_args()

    cfg = get_state(args.state)
    root, raw, processed, grid_path = get_paths(cfg["abbr"])
    crs_proj = cfg["utm_epsg"]
    print(f"\n=== 02_indicators: {cfg['name']} ({cfg['abbr']}) ===")

    state = gpd.read_file(raw / "state.geojson")
    dc_gdf = gpd.read_file(raw / "datacenters.geojson") if (raw / "datacenters.geojson").exists() else \
             gpd.GeoDataFrame(columns=["source", "geometry"], crs=CRS)
    tx_gdf = gpd.read_file(raw / "transmission.geojson") if (raw / "transmission.geojson").exists() else \
             gpd.GeoDataFrame(columns=["geometry"], crs=CRS)

    print(f"Building {CELL_SIZE}° fishnet grid...")
    grid = create_fishnet(state)
    print(f"  {len(grid)} cells")

    print("Transmission proximity (tx_score)...")
    if len(tx_gdf) > 0:
        tx_proj = tx_gdf.to_crs(crs_proj)
        tx_union = tx_proj.geometry.unary_union
        grid_proj = grid.to_crs(crs_proj)
        centroids = list(grid_proj.geometry.centroid)
        grid["tx_dist_m"] = [tx_union.distance(pt) for pt in centroids]
        grid["tx_score"] = 1.0 - (grid["tx_dist_m"] / grid["tx_dist_m"].max())
    else:
        print("  No transmission data; tx_score=0.5 (neutral)")
        grid["tx_score"] = 0.5
    print(f"  tx_score: {grid['tx_score'].min():.3f} - {grid['tx_score'].max():.3f}")

    print("Precipitation / water availability (water_score)...")
    precip_df = fetch_precip(state, raw)
    centroids_ll = grid.geometry.centroid
    grid["ann_precip_mm"] = idw(
        precip_df["lat"].values, precip_df["lon"].values, precip_df["ann_precip_mm"].values,
        np.array([p.y for p in centroids_ll]), np.array([p.x for p in centroids_ll]),
    )
    p05, p95 = grid["ann_precip_mm"].quantile([0.05, 0.95])
    grid["water_score"] = ((grid["ann_precip_mm"] - p05) / (p95 - p05)).clip(0, 1)
    print(f"  water_score: {grid['water_score'].min():.3f} - {grid['water_score'].max():.3f}")

    print("Community burden / EJ score (ej_score)...")
    tracts = fetch_tracts(cfg["fips"], raw)
    df_acs = fetch_acs(cfg["fips"], raw)
    tracts["GEOID"] = tracts["GEOID"].astype(str).str.zfill(11)
    df_acs["GEOID"] = df_acs["GEOID"].astype(str).str.zfill(11)
    ej_gdf = tracts[["GEOID", "geometry"]].merge(
        df_acs[["GEOID", "demog_index"]], on="GEOID", how="left"
    )
    grid_pts = gpd.GeoDataFrame(
        {"cell_id": grid["cell_id"]}, geometry=grid.geometry.centroid, crs=CRS
    )
    joined = gpd.sjoin(
        grid_pts, ej_gdf[["GEOID", "demog_index", "geometry"]],
        how="left", predicate="within"
    )
    burden_by_cell = joined.groupby("cell_id")["demog_index"].mean()
    grid["demog_index"] = grid["cell_id"].map(burden_by_cell)
    q01, q99 = grid["demog_index"].quantile([0.01, 0.99])
    grid["ej_score"] = 1.0 - ((grid["demog_index"] - q01) / (q99 - q01)).clip(0, 1)
    grid["ej_score"] = grid["ej_score"].fillna(grid["ej_score"].median())
    print(f"  ej_score: {grid['ej_score'].min():.3f} - {grid['ej_score'].max():.3f}")

    print("Population exposure (pop_exposure_score)...")
    tracts_pop = tracts[["GEOID", "geometry"]].merge(
        df_acs[["GEOID", "pop"]], on="GEOID", how="left"
    )
    tracts_proj = tracts_pop.to_crs(crs_proj).copy()
    tracts_proj["area_km2"] = tracts_proj.geometry.area / 1e6
    tracts_proj["pop_density"] = tracts_proj["pop"] / tracts_proj["area_km2"].clip(lower=0.01)
    tracts_pop["pop_density"] = tracts_proj["pop_density"].values
    grid_pts2 = gpd.GeoDataFrame(
        {"cell_id": grid["cell_id"]}, geometry=grid.geometry.centroid, crs=CRS
    )
    joined_pop = gpd.sjoin(
        grid_pts2, tracts_pop[["pop_density", "geometry"]],
        how="left", predicate="within"
    )
    density_by_cell = joined_pop.groupby("cell_id")["pop_density"].mean()
    grid["pop_density"] = grid["cell_id"].map(density_by_cell).fillna(0)
    p95_dens = grid["pop_density"].quantile(0.95)
    grid["pop_exposure_score"] = (1.0 - (grid["pop_density"] / p95_dens).clip(0, 1))
    print(f"  pop_exposure_score: {grid['pop_exposure_score'].min():.3f} - {grid['pop_exposure_score'].max():.3f}")

    grid_out = grid.drop(
        columns=["tx_dist_m", "ann_precip_mm", "demog_index", "pop_density"],
        errors="ignore",
    )
    grid_out.to_file(grid_path, driver="GeoJSON")
    print(f"\nSaved grid ({len(grid_out)} cells) to {grid_path.name}")

    print("Indicator map...")
    plot_indicators(cfg, state, dc_gdf, grid_out, processed)
    print("Done.")


if __name__ == "__main__":
    main()
