"""
01_basemap.py — Download base layers for a given state.

Outputs (all in data/{STATE}/raw/):
  state.geojson           — Census TIGER 2022 state boundary
  datacenters.geojson     — OSM data centers (man_made=data_centre)
  transmission.geojson    — OSM HV lines (power=line, voltage >= 100kV)
  eia860_plants.geojson   — EIA Form 860 power plants

Usage:
  python 01_basemap.py WA
"""

import argparse
import io
import sys
import warnings
import zipfile
from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).parent))
from config import get_state, get_paths

warnings.filterwarnings("ignore")
CRS = "EPSG:4326"


def fetch_state_boundary(abbr, fips, raw):
    path = raw / "state.geojson"
    if path.exists():
        return gpd.read_file(path)
    print("  Downloading Census TIGER state boundaries...")
    url = "https://www2.census.gov/geo/tiger/TIGER2022/STATE/tl_2022_us_state.zip"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(raw / "_tiger_states")
    states = gpd.read_file(raw / "_tiger_states" / "tl_2022_us_state.shp")
    state = states[states["STUSPS"] == abbr].to_crs(CRS)
    state.to_file(path, driver="GeoJSON")
    print(f"  Saved {path.name}")
    return state


def fetch_osm_datacenters(bbox, state_union):
    west, south, east, north = bbox
    query = f"""
[out:json][timeout:45];
(
  node["man_made"="data_centre"]({south},{west},{north},{east});
  way["man_made"="data_centre"]({south},{west},{north},{east});
  relation["man_made"="data_centre"]({south},{west},{north},{east});
);
out center;
"""
    r = requests.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": query},
        headers={"User-Agent": "datacenter-siting-research/1.0"},
        timeout=60,
    )
    r.raise_for_status()
    records = []
    for el in r.json().get("elements", []):
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat and lon:
            records.append({
                "name": el.get("tags", {}).get("name", "Unknown"),
                "operator": el.get("tags", {}).get("operator", ""),
                "lat": lat, "lon": lon, "source": "OSM",
            })
    df = pd.DataFrame(records)
    if df.empty:
        return gpd.GeoDataFrame(columns=["name", "operator", "lat", "lon", "source", "geometry"], crs=CRS)
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=CRS)
    return gdf[gdf.within(state_union)].reset_index(drop=True)


def fetch_osm_transmission(bbox):
    west, south, east, north = bbox
    query = f"""
[out:json][timeout:150][maxsize:134217728];
(
  way["power"="line"]["voltage"~"^[1-9][0-9]{{5}}"](
    {south},{west},{north},{east}
  );
);
out geom;
"""
    r = requests.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": query},
        headers={"User-Agent": "datacenter-siting-research/1.0"},
        timeout=180,
    )
    r.raise_for_status()
    lines = []
    for el in r.json().get("elements", []):
        if el.get("type") == "way" and "geometry" in el:
            coords = [(n["lon"], n["lat"]) for n in el["geometry"]]
            if len(coords) >= 2:
                lines.append({
                    "osm_id": el.get("id"),
                    "voltage": el.get("tags", {}).get("voltage", ""),
                    "name": el.get("tags", {}).get("name", ""),
                    "geometry": LineString(coords),
                })
    return gpd.GeoDataFrame(lines, crs=CRS) if lines else gpd.GeoDataFrame(columns=["geometry"], crs=CRS)


def fetch_eia860(abbr, raw):
    path = raw / "eia860_plants.geojson"
    if path.exists():
        return gpd.read_file(path)
    print("  Downloading EIA Form 860 (2023)...")
    url = "https://www.eia.gov/electricity/data/eia860/archive/xls/eia8602023.zip"
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        pf = next(f for f in z.namelist() if "2___Plant" in f and f.endswith(".xlsx"))
        with z.open(pf) as f:
            plants = pd.read_excel(f, sheet_name=0, skiprows=1, engine="openpyxl",
                                   usecols=["Plant Code", "Plant Name", "State", "Latitude", "Longitude"])
        gf = next(f for f in z.namelist() if "3_1_Generator" in f and f.endswith(".xlsx"))
        with z.open(gf) as f:
            gens = pd.read_excel(f, sheet_name=0, skiprows=1, engine="openpyxl",
                                 usecols=["Plant Code", "Energy Source 1", "Nameplate Capacity (MW)", "Status"])
    plants.columns = plants.columns.str.strip()
    gens.columns = gens.columns.str.strip()
    gens = gens[gens["Status"].isin(["OP", "OA", "OS"])]
    gens["Nameplate Capacity (MW)"] = pd.to_numeric(gens["Nameplate Capacity (MW)"], errors="coerce")
    agg = (gens.groupby("Plant Code")
           .agg(capacity_mw=("Nameplate Capacity (MW)", "sum"),
                fuel=("Energy Source 1", lambda x: x.mode().iloc[0] if len(x) else ""))
           .reset_index())
    state_plants = plants[plants["State"] == abbr].copy()
    state_plants["Latitude"] = pd.to_numeric(state_plants["Latitude"], errors="coerce")
    state_plants["Longitude"] = pd.to_numeric(state_plants["Longitude"], errors="coerce")
    state_plants = state_plants.dropna(subset=["Latitude", "Longitude"]).merge(agg, on="Plant Code", how="left")
    state_plants = state_plants.rename(columns={"Plant Name": "name", "Latitude": "lat", "Longitude": "lon"})
    gdf = gpd.GeoDataFrame(state_plants,
                           geometry=gpd.points_from_xy(state_plants["lon"], state_plants["lat"]),
                           crs=CRS)
    gdf[["name", "fuel", "capacity_mw", "lat", "lon", "geometry"]].to_file(path, driver="GeoJSON")
    print(f"  Saved {len(gdf)} plants to {path.name}")
    return gdf


def plot_basemap(cfg, state, dc_gdf, tx_gdf, plants_gdf, processed):
    fig, ax = plt.subplots(figsize=(14, 9), facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    state.boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.2, zorder=1)

    if "voltage" in tx_gdf.columns and tx_gdf["voltage"].notna().any():
        def parse_v(v):
            try: return float(str(v).split(";")[0].replace(",", ""))
            except: return 0.0
        tx_gdf["_v"] = tx_gdf["voltage"].apply(parse_v)
        tx_gdf[tx_gdf["_v"] >= 230000].plot(ax=ax, color="#5a9aba", linewidth=0.9, alpha=0.8, zorder=2)
        tx_gdf[tx_gdf["_v"] < 230000].plot(ax=ax, color="#3a5a7a", linewidth=0.4, alpha=0.5, zorder=2)
    else:
        tx_gdf.plot(ax=ax, color="#5a9aba", linewidth=0.6, alpha=0.7, zorder=2)

    if "fuel" in plants_gdf.columns and len(plants_gdf) > 0:
        fuel_colors = {"WAT": "#2196F3", "NG": "#FF9800", "WND": "#4CAF50", "SUN": "#FFEB3B", "NUC": "#9C27B0"}
        colors = plants_gdf["fuel"].map(fuel_colors).fillna("#888888").values
        sizes = pd.to_numeric(plants_gdf["capacity_mw"], errors="coerce").fillna(10).clip(10, 5000).values / 50
        ax.scatter(plants_gdf.geometry.x, plants_gdf.geometry.y,
                   c=colors, s=sizes.clip(10, 200), alpha=0.7, zorder=4, linewidths=0)

    colors_src = {"OSM": "#FF4444", "reported": "#FF6B35", "proposed": "#FFB347"}
    for src, grp in dc_gdf.groupby("source"):
        ax.scatter(grp.geometry.x, grp.geometry.y, c=colors_src.get(src, "#FF4444"),
                   s=120, marker="D", zorder=6, edgecolors="white", linewidths=0.5)

    patches = [mpatches.Patch(color=c, label=l) for c, l in [
        ("#5a9aba", "TX >= 230kV"), ("#3a5a7a", "TX < 230kV"),
        ("#FF6B35", "Data center"), ("#2196F3", "Hydro"), ("#FF9800", "Gas"),
    ]]
    leg = ax.legend(handles=patches, loc="lower left", facecolor="#1a1a2e",
                    edgecolor="#4a4a6a", fontsize=8, framealpha=0.4)
    for t in leg.get_texts():
        t.set_color("white")

    ax.set_title(f"{cfg['name']}: Data Centers vs. Electrical Infrastructure",
                 color="white", fontsize=14, pad=12)
    ax.tick_params(colors="#888888")
    for s in ax.spines.values():
        s.set_edgecolor("#4a4a6a")
    plt.tight_layout()
    out = processed / "basemap.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved {out.name}")


def main():
    parser = argparse.ArgumentParser(description="Download base layers for a US state.")
    parser.add_argument("state", help="Two-letter state abbreviation (e.g. WA)")
    args = parser.parse_args()

    cfg = get_state(args.state)
    root, raw, processed, grid_path = get_paths(cfg["abbr"])
    bbox = cfg["bbox"]
    print(f"\n=== 01_basemap: {cfg['name']} ({cfg['abbr']}) ===")

    print("State boundary...")
    state = fetch_state_boundary(cfg["abbr"], cfg["fips"], raw)
    state_union = state.geometry.unary_union
    print(f"  {len(state)} feature(s)")

    print("OSM data centers...")
    dc_path = raw / "datacenters.geojson"
    if dc_path.exists():
        dc_gdf = gpd.read_file(dc_path)
        print(f"  {len(dc_gdf)} cached")
    else:
        try:
            dc_gdf = fetch_osm_datacenters(bbox, state_union)
        except Exception as e:
            print(f"  OSM failed ({e}); saving empty file")
            dc_gdf = gpd.GeoDataFrame(columns=["name", "operator", "source", "geometry"], crs=CRS)
        dc_gdf.to_file(dc_path, driver="GeoJSON")
        print(f"  Saved {len(dc_gdf)} data centers")

    print("OSM transmission lines...")
    tx_path = raw / "transmission.geojson"
    if tx_path.exists():
        tx_gdf = gpd.read_file(tx_path)
        print(f"  {len(tx_gdf)} cached")
    else:
        try:
            tx_gdf = fetch_osm_transmission(bbox)
        except Exception as e:
            print(f"  OSM failed ({e}); saving empty file")
            tx_gdf = gpd.GeoDataFrame(columns=["geometry"], crs=CRS)
        tx_gdf.to_file(tx_path, driver="GeoJSON")
        print(f"  Saved {len(tx_gdf)} transmission segments")

    print("EIA 860 power plants...")
    plants_gdf = fetch_eia860(cfg["abbr"], raw)
    print(f"  {len(plants_gdf)} plants")

    print("Basemap plot...")
    plot_basemap(cfg, state, dc_gdf, tx_gdf, plants_gdf, processed)
    print(f"\nDone. Outputs in {raw}")


if __name__ == "__main__":
    main()
