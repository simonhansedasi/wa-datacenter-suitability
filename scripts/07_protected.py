"""
07_protected.py — Compute protected land hard gate.

Adds to grid_scores.geojson:
  protected_score — 0.0 if > PROT_GATE overlap with protected land, else 1.0

Sources:
  Esri USA Federal Lands (NPS, USFWS, DoD, Forest Service; BLM excluded)
  Census TIGER AIANNH (tribal lands)

Usage:
  python 07_protected.py WA
"""

import argparse
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from config import get_state, get_paths

warnings.filterwarnings("ignore")
CRS = "EPSG:4326"
DARK_BG = "#1a1a2e"
WHITE = "white"
PROT_GATE = 0.25  # > 25% protected overlap = hard gate

FED_LANDS_URL = ("https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/"
                 "services/USA_Federal_Lands/FeatureServer/0/query")
TIGER_URL = ("https://tigerweb.geo.census.gov/arcgis/rest/services/"
             "TIGERweb/AIANNHA/MapServer/3/query")

AGENCIES = ("'National Park Service','Fish and Wildlife Service',"
            "'Department of Defense','Forest Service'")


def fetch_federal_lands(bbox_str, cache_path):
    if cache_path.exists():
        gdf = gpd.read_file(cache_path)
        if 'source' not in gdf.columns:
            gdf["source"] = "Esri Federal Lands"
        return gdf
    features = []
    offset = 0
    while True:
        r = requests.get(FED_LANDS_URL, params={
            "where": f"Agency IN ({AGENCIES})",
            "geometry": bbox_str, "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects", "inSR": "4326",
            "outFields": "Agency,unit_name", "returnGeometry": "true",
            "f": "geojson", "resultRecordCount": 1000, "resultOffset": offset,
        }, timeout=120)
        r.raise_for_status()
        batch = r.json().get("features", [])
        features.extend(batch)
        print(f"    {len(features)} federal land features...")
        if len(batch) < 1000:
            break
        offset += 1000
    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS)
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid]
    gdf["source"] = "Esri Federal Lands"
    gdf.to_file(cache_path, driver="GeoJSON")
    print(f"    Saved {len(gdf)} federal land polygons")
    return gdf


def fetch_tribal_lands(bbox_str, cache_path):
    if cache_path.exists():
        gdf = gpd.read_file(cache_path)
        if 'source' not in gdf.columns:
            gdf["source"] = "TIGER AIANNH"
        return gdf
    r = requests.get(TIGER_URL, params={
        "geometry": bbox_str, "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects", "inSR": "4326",
        "outFields": "NAME,AIANNHNS", "returnGeometry": "true", "f": "geojson",
    }, timeout=60)
    r.raise_for_status()
    feats = r.json().get("features", [])
    if feats:
        gdf = gpd.GeoDataFrame.from_features(feats, crs=CRS)
        gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid]
    else:
        gdf = gpd.GeoDataFrame(columns=["NAME", "geometry"], crs=CRS)
    gdf["source"] = "TIGER AIANNH"
    gdf.to_file(cache_path, driver="GeoJSON")
    print(f"    Saved {len(gdf)} tribal land polygons")
    return gdf


def plot_protected(cfg, state, dc_gdf, grid, gated, prot_dissolved, processed):
    grid_proj = grid.to_crs(cfg["utm_epsg"])
    state_proj = state.to_crs(cfg["utm_epsg"])
    prot_proj = prot_dissolved.to_crs(cfg["utm_epsg"]) if len(prot_dissolved) > 0 else prot_dissolved
    dc_proj = dc_gdf.to_crs(cfg["utm_epsg"]) if len(dc_gdf) > 0 else dc_gdf

    plt.rcParams.update({"text.color": WHITE, "axes.labelcolor": WHITE,
                         "xtick.color": WHITE, "ytick.color": WHITE, "font.size": 16})
    fig, ax = plt.subplots(1, 1, figsize=(12, 10), facecolor=DARK_BG)
    ax.set_facecolor(DARK_BG)
    state_proj.boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0, zorder=1)
    grid_proj[gated].plot(ax=ax, color="#1e2e1e", alpha=0.85, zorder=2)
    grid_proj[~gated].plot(ax=ax, color="#3a4a5a", alpha=0.45, zorder=2)
    if len(prot_proj) > 0:
        prot_proj.boundary.plot(ax=ax, color="#4a8a4a", linewidth=0.6, alpha=0.7, zorder=3)
    if len(dc_proj) > 0:
        rep = dc_proj[dc_proj["source"].isin(["reported", "OSM"])]
        prop = dc_proj[dc_proj["source"] == "proposed"]
        ax.scatter(rep.geometry.x, rep.geometry.y, c=WHITE, s=100, marker="D",
                   zorder=5, edgecolors="black", linewidths=0.8)
        ax.scatter(prop.geometry.x, prop.geometry.y, facecolors="none", s=100,
                   marker="D", zorder=5, edgecolors="black", linewidths=1.5)
    gated_patch = mpatches.Patch(color="#1e2e1e", alpha=0.9,
                                 label=f"Gated: > {PROT_GATE:.0%} protected land")
    clear_patch = mpatches.Patch(color="#3a4a5a", alpha=0.6, label="Available")
    leg = ax.legend(handles=[gated_patch, clear_patch], loc="lower right",
                    facecolor=DARK_BG, edgecolor="#4a4a6a", fontsize=12)
    for t in leg.get_texts():
        t.set_color(WHITE)
    ax.set_title(
        f"{cfg['name']}: Protected Land Gate\n"
        "(Esri Federal Lands + TIGER Tribal; gate > 25% overlap)\n"
        "White filled = existing DC  /  outline = proposed DC",
        color=WHITE, fontsize=18, pad=10, linespacing=1.4,
    )
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for s in ax.spines.values():
        s.set_edgecolor("#4a4a6a")
    plt.tight_layout()
    out = processed / "protected_land.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved {out.name}")


def main():
    parser = argparse.ArgumentParser(description="Compute protected land gate.")
    parser.add_argument("state", help="Two-letter state abbreviation (e.g. WA)")
    args = parser.parse_args()

    cfg = get_state(args.state)
    root, raw, processed, grid_path = get_paths(cfg["abbr"])
    crs_proj = cfg["utm_epsg"]
    bbox_str = cfg["bbox_str"]
    print(f"\n=== 07_protected: {cfg['name']} ({cfg['abbr']}) ===")

    state = gpd.read_file(raw / "state.geojson")
    dc_gdf = gpd.read_file(raw / "datacenters.geojson") if (raw / "datacenters.geojson").exists() else \
             gpd.GeoDataFrame(columns=["source", "geometry"], crs=CRS)
    grid = gpd.read_file(grid_path)
    print(f"Grid: {len(grid)} cells")

    print("Federal lands (Esri)...")
    fed = fetch_federal_lands(bbox_str, raw / "federal_lands.geojson")

    print("Tribal lands (TIGER)...")
    tribal = fetch_tribal_lands(bbox_str, raw / "tribal_tiger.geojson")

    print("Merging and dissolving protected areas...")
    all_prot = gpd.GeoDataFrame(
        pd.concat([fed[["geometry", "source"]], tribal[["geometry", "source"]]], ignore_index=True),
        crs=CRS,
    )
    all_proj = all_prot.to_crs(crs_proj)
    prot_dissolved = all_proj.dissolve().reset_index(drop=True)

    print("Computing protected overlap per cell...")
    grid_proj = grid.to_crs(crs_proj).copy()
    grid_proj["cell_id"] = grid_proj.index
    grid_proj["cell_area"] = grid_proj.geometry.area

    if len(prot_dissolved) > 0:
        isect = gpd.overlay(
            grid_proj[["cell_id", "cell_area", "geometry"]],
            prot_dissolved[["geometry"]],
            how="intersection", keep_geom_type=False,
        )
        isect["prot_area"] = isect.geometry.area
        prot_by_cell = isect.groupby("cell_id")["prot_area"].sum()
        cell_areas = grid_proj.set_index("cell_id")["cell_area"]
        grid["protected_frac"] = (
            prot_by_cell.reindex(cell_areas.index, fill_value=0) / cell_areas
        ).clip(0, 1).values
    else:
        grid["protected_frac"] = 0.0

    gated = grid["protected_frac"] > PROT_GATE
    grid["protected_score"] = 1.0
    grid.loc[gated, "protected_score"] = 0.0
    n_gated = gated.sum()
    print(f"  {n_gated} cells gated ({n_gated/len(grid):.1%}); {(~gated).sum()} clear")

    grid_out = grid.drop(columns=["protected_frac"], errors="ignore")
    grid_out.to_file(grid_path, driver="GeoJSON")
    print(f"\nSaved grid to {grid_path.name}")

    print("Protected land map...")
    plot_protected(cfg, state, dc_gdf, grid_out, gated, prot_dissolved, processed)
    print("Done.")


if __name__ == "__main__":
    main()
