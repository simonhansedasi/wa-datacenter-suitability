"""
06_terrain.py — Compute terrain flatness score from SRTM1 tiles.

Adds to grid_scores.geojson:
  flatness_score — 0.0 if < FLAT_GATE (hard gate), else normalized flat_frac

Data: SRTM1 HGT tiles from AWS S3 (public), parsed with numpy (no GDAL).
Tiles cached under data/{STATE}/raw/srtm_tiles/.

Usage:
  python 06_terrain.py WA
"""

import argparse
import gzip
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).parent))
from config import get_state, get_paths

warnings.filterwarnings("ignore")
CRS = "EPSG:4326"
DARK_BG = "#1a1a2e"
WHITE = "white"

TILE_SIZE = 3601        # SRTM1 1-degree tiles: 3601x3601
DOWNSAMPLE = 3          # 30m -> ~90m (reduces array ~9x)
NODATA_VAL = -32768
FLAT_GATE = 0.03        # < 3% flat area = hard gate (unbuildable)
SLOPE_THRESHOLD = 5.0   # degrees: flat is slope < 5 deg


def srtm_tile_range(bbox):
    """Return (lat_tiles, lon_tiles) covering the bbox.
    lat_tiles: list of integer N-latitudes (tile covers lat to lat+1), N->S order
    lon_tiles: list of integer W-longitudes as positive (e.g. W120 = 120), W->E order
    """
    west, south, east, north = bbox
    lat_min = int(np.floor(south))
    lat_max = int(np.floor(north))
    # For SRTM: N?W117 covers lon -117 to -116. Tile ID = ceil(abs(lon)).
    lon_min = int(np.ceil(abs(east)))   # easternmost tile (smallest W number)
    lon_max = int(np.ceil(abs(west)))   # westernmost tile (largest W number)
    lat_tiles = list(range(lat_min, lat_max + 1))[::-1]  # N->S (descending)
    lon_tiles = list(range(lon_min, lon_max + 1))         # W->E ascending
    return lat_tiles, lon_tiles


def download_tile(lat, lon, tile_dir):
    lat_tag = f"N{lat:02d}"
    filename = f"{lat_tag}W{lon:03d}.hgt"
    path = tile_dir / filename
    if path.exists():
        return path
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/skadi/{lat_tag}/{filename}.gz"
    print(f"    Fetching {filename}...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    path.write_bytes(gzip.decompress(r.content))
    return path


def load_tile(path):
    data = np.frombuffer(path.read_bytes(), dtype=">i2").reshape(TILE_SIZE, TILE_SIZE).astype(np.float32)
    data[data == NODATA_VAL] = np.nan
    return data


def build_dem(lat_tiles, lon_tiles, tile_dir):
    rows = []
    for lat in lat_tiles:
        cols = []
        for lon in lon_tiles:
            try:
                tile = load_tile(download_tile(lat, lon, tile_dir))
            except Exception as e:
                print(f"    Tile N{lat:02d}W{lon:03d} failed ({e}); filled with NaN")
                tile = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype=np.float32)
            cols.append(tile[:-1, :-1])  # drop edge overlap
        rows.append(np.hstack(cols))
    return np.vstack(rows)


def compute_slope(dem, lat_tiles, lon_tiles):
    north = float(max(lat_tiles) + 1)
    west = float(-max(lon_tiles))
    res = DOWNSAMPLE / 3600.0  # degrees per pixel after downsampling

    if DOWNSAMPLE > 1:
        dem = dem[::DOWNSAMPLE, ::DOWNSAMPLE]

    lat_1d = north - np.arange(dem.shape[0]) * res
    lon_1d = west + np.arange(dem.shape[1]) * res

    dy_m = res * 110540.0
    dx_m = res * np.cos(np.radians(lat_1d[:, np.newaxis])) * 111320.0
    dem_filled = np.where(np.isnan(dem), np.nanmedian(dem), dem)
    dz_dy, dz_dx = np.gradient(dem_filled)
    slope_deg = np.degrees(np.arctan(np.sqrt((dz_dx / dx_m) ** 2 + (dz_dy / dy_m) ** 2)))
    slope_deg[np.isnan(dem)] = np.nan
    return slope_deg, lat_1d, lon_1d


def compute_flat_fracs(grid, slope_deg, lat_1d, lon_1d):
    flat_fracs = []
    for _, cell in grid.iterrows():
        minx, miny, maxx, maxy = cell.geometry.bounds
        r0 = int(np.searchsorted(-lat_1d, -maxy))
        r1 = int(np.searchsorted(-lat_1d, -miny)) + 1
        c0 = int(np.searchsorted(lon_1d, minx))
        c1 = int(np.searchsorted(lon_1d, maxx)) + 1
        r0, r1 = max(0, r0), min(slope_deg.shape[0], r1)
        c0, c1 = max(0, c0), min(slope_deg.shape[1], c1)
        patch = slope_deg[r0:r1, c0:c1]
        valid = patch[~np.isnan(patch)]
        flat_fracs.append(float(np.mean(valid < SLOPE_THRESHOLD)) if len(valid) > 0 else 0.0)
    return flat_fracs


def plot_terrain(cfg, state, dc_gdf, grid, buildable, processed):
    grid_proj = grid.to_crs(cfg["utm_epsg"])
    state_proj = state.to_crs(cfg["utm_epsg"])
    dc_proj = dc_gdf.to_crs(cfg["utm_epsg"]) if len(dc_gdf) > 0 else dc_gdf
    build_plot = grid_proj[buildable]
    gated_plot = grid_proj[~buildable]

    plt.rcParams.update({"text.color": WHITE, "axes.labelcolor": WHITE,
                         "xtick.color": WHITE, "ytick.color": WHITE, "font.size": 16})
    fig, ax = plt.subplots(1, 1, figsize=(12, 10), facecolor=DARK_BG)
    ax.set_facecolor(DARK_BG)
    state_proj.boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0, zorder=1)
    if len(gated_plot) > 0:
        gated_plot.plot(ax=ax, color="#2a2a3a", alpha=0.80, zorder=2)
    n0 = len(fig.axes)
    build_plot.plot(column="flatness_score", ax=ax, cmap="YlGn", vmin=0, vmax=1,
                    legend=True, legend_kwds={"shrink": 0.65, "label": "0=little flat / 1=most flat"},
                    alpha=0.85, zorder=3)
    if len(fig.axes) > n0:
        cb = fig.axes[-1]; cb.tick_params(labelsize=14, colors=WHITE)
        cb.yaxis.label.set_color(WHITE)
    if len(dc_proj) > 0:
        rep = dc_proj[dc_proj["source"].isin(["reported", "OSM"])]
        prop = dc_proj[dc_proj["source"] == "proposed"]
        ax.scatter(rep.geometry.x, rep.geometry.y, c=WHITE, s=100, marker="D",
                   zorder=5, edgecolors="black", linewidths=0.8)
        ax.scatter(prop.geometry.x, prop.geometry.y, facecolors="none", s=100,
                   marker="D", zorder=5, edgecolors="black", linewidths=1.5)
    gated_patch = mpatches.Patch(color="#2a2a3a", alpha=0.9,
                                 label=f"Gated: < {FLAT_GATE:.0%} flat area")
    leg = ax.legend(handles=[gated_patch], loc="lower right",
                    facecolor=DARK_BG, edgecolor="#4a4a6a", fontsize=12)
    for t in leg.get_texts():
        t.set_color(WHITE)
    ax.set_title(
        f"{cfg['name']}: Terrain Flatness (SRTM1 ~90m)\n"
        f"(Fraction with slope < {SLOPE_THRESHOLD}deg; hard gate at {FLAT_GATE:.0%})\n"
        "White filled = existing DC  /  outline = proposed DC",
        color=WHITE, fontsize=18, pad=10, linespacing=1.4,
    )
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for s in ax.spines.values():
        s.set_edgecolor("#4a4a6a")
    plt.tight_layout()
    out = processed / "terrain_flatness.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved {out.name}")


def main():
    parser = argparse.ArgumentParser(description="Compute terrain flatness score from SRTM1.")
    parser.add_argument("state", help="Two-letter state abbreviation (e.g. WA)")
    args = parser.parse_args()

    cfg = get_state(args.state)
    root, raw, processed, grid_path = get_paths(cfg["abbr"])
    tile_dir = raw / "srtm_tiles"
    tile_dir.mkdir(exist_ok=True)
    print(f"\n=== 06_terrain: {cfg['name']} ({cfg['abbr']}) ===")

    state = gpd.read_file(raw / "state.geojson")
    dc_gdf = gpd.read_file(raw / "datacenters.geojson") if (raw / "datacenters.geojson").exists() else \
             gpd.GeoDataFrame(columns=["source", "geometry"], crs=CRS)
    grid = gpd.read_file(grid_path)
    print(f"Grid: {len(grid)} cells")

    lat_tiles, lon_tiles = srtm_tile_range(cfg["bbox"])
    print(f"SRTM tiles: {len(lat_tiles)} lat x {len(lon_tiles)} lon = {len(lat_tiles)*len(lon_tiles)} tiles")

    print("Building DEM...")
    dem = build_dem(lat_tiles, lon_tiles, tile_dir)
    print(f"  DEM shape: {dem.shape} raw ({DOWNSAMPLE}x downsample -> ~{DOWNSAMPLE*30}m/px)")

    print("Computing slope...")
    slope_deg, lat_1d, lon_1d = compute_slope(dem, lat_tiles, lon_tiles)
    print(f"  Slope range: {np.nanmin(slope_deg):.1f} - {np.nanmax(slope_deg):.1f} deg")

    print("Computing flat_frac per cell...")
    flat_fracs = compute_flat_fracs(grid, slope_deg, lat_1d, lon_1d)
    grid["flat_frac"] = flat_fracs
    print(f"  flat_frac: {grid.flat_frac.min():.3f} - {grid.flat_frac.max():.3f}")

    buildable = grid["flat_frac"] >= FLAT_GATE
    n_gated = (~buildable).sum()
    p95 = grid.loc[buildable, "flat_frac"].quantile(0.95)
    grid["flatness_score"] = 0.0
    grid.loc[buildable, "flatness_score"] = (grid.loc[buildable, "flat_frac"] / p95).clip(0, 1)
    # slope_score: continuous normalized version, no hard gate zeroing — for use as weighted slider
    grid["slope_score"] = (grid["flat_frac"] / p95).clip(0, 1)
    print(f"  Gate: {n_gated} cells gated ({n_gated/len(grid):.1%}); p95={p95:.3f}")

    grid_out = grid.drop(columns=["flat_frac"], errors="ignore")
    grid_out.to_file(grid_path, driver="GeoJSON")
    print(f"\nSaved grid to {grid_path.name}")

    print("Terrain map...")
    plot_terrain(cfg, state, dc_gdf, grid_out, buildable, processed)
    print("Done.")


if __name__ == "__main__":
    main()
