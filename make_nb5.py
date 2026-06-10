"""Build 05_geothermal.ipynb programmatically."""
import json

def md(text, cell_id):
    return {
        'cell_type': 'markdown', 'id': cell_id, 'metadata': {},
        'source': [line + '\n' for line in text.split('\n')]
    }

def code(text, cell_id):
    return {
        'cell_type': 'code', 'id': cell_id, 'metadata': {},
        'source': [line + '\n' for line in text.split('\n')],
        'outputs': [], 'execution_count': None
    }

cells = []

# Cell 0: title
cells.append(md(
    '# Notebook 5: Geothermal Resource Proximity\n'
    '\n'
    'Adds a geothermal opportunity indicator using real measured subsurface heat flow:\n'
    '\n'
    '| Field | Detail |\n'
    '|---|---|\n'
    '| Source | IHFC Global Heat Flow Database 2024 (GHFDB Release 2024) |\n'
    '| Citation | Lucazeau et al. (2025), DOI 10.5880/fidgeo.2024.014 |\n'
    '| Records used | 664 US measurements within Washington State bounding box |\n'
    '| Method | IDW interpolation (k=8 neighbors, power=2) of capped q values |\n'
    '| Score direction | Higher = elevated heat flow = greater geothermal energy opportunity |\n'
    '\n'
    'Geothermal heat flow (mW/m2) is a proxy for the viability of co-located '
    'enhanced geothermal or direct-use heating systems that could power or '
    'cool a data center. High values cluster along the Cascade volcanic arc.',
    'nb5_0000'
))

# Cell 1: imports
cells.append(code(
    'import warnings\n'
    'from pathlib import Path\n'
    '\n'
    'import geopandas as gpd\n'
    'import matplotlib.pyplot as plt\n'
    'import numpy as np\n'
    'import pandas as pd\n'
    'from scipy.spatial import cKDTree\n'
    '\n'
    'warnings.filterwarnings("ignore")\n'
    '\n'
    'RAW       = Path("data/raw")\n'
    'PROCESSED = Path("data/processed")\n'
    'DARK_BG   = "#1a1a2e"\n'
    'WHITE     = "white"\n'
    '\n'
    'plt.rcParams.update({\n'
    '    "text.color": WHITE, "axes.labelcolor": WHITE,\n'
    '    "xtick.color": WHITE, "ytick.color": WHITE, "font.size": 16,\n'
    '})\n'
    'print("Imports OK")',
    'nb5_0001'
))

# Cell 2: load grid
cells.append(md('## 1. Load grid and boundaries', 'nb5_0002'))

cells.append(code(
    'wa     = gpd.read_file(RAW / "wa_state.geojson").to_crs("EPSG:32610")\n'
    'dc_gdf = gpd.read_file(RAW / "datacenters.geojson").to_crs("EPSG:32610")\n'
    'grid   = gpd.read_file("static/grid_scores.geojson").to_crs("EPSG:32610")\n'
    '\n'
    'grid["centroid"] = grid.geometry.centroid\n'
    'tgt_x = np.array([c.x for c in grid.centroid])\n'
    'tgt_y = np.array([c.y for c in grid.centroid])\n'
    'grid_coords = np.column_stack([tgt_x, tgt_y])\n'
    '\n'
    'print(f"Grid: {len(grid)} cells")\n'
    'print(f"Existing columns: {[c for c in grid.columns if c != \'geometry\']}")',
    'nb5_0003'
))

# Cell 3: load heat flow data
cells.append(md(
    '## 2. Load GHFDB Heat Flow Measurements\n'
    '\n'
    'Using the filtered CSV (`data/raw/wa_heatflow.csv`) derived from the '
    'IHFC 2024 GHFDB shapefile. The `q` column is surface heat flow in mW/m2.\n'
    '\n'
    'Values are capped at the 95th percentile (162 mW/m2) before IDW '
    'interpolation to prevent the extreme volcanic hydrothermal measurements '
    'near Mount Baker (up to 5146 mW/m2) from dominating the spatial signal.',
    'nb5_0004'
))

cells.append(code(
    'hf = pd.read_csv(RAW / "wa_heatflow.csv")\n'
    'print(f"Heat flow records: {len(hf)}")\n'
    'print(f"q range: {hf[\'q\'].min():.1f} - {hf[\'q\'].max():.1f} mW/m2")\n'
    '\n'
    '# Cap at 95th percentile to prevent hydrothermal outliers from dominating IDW\n'
    'q95 = np.percentile(hf["q"], 95)\n'
    'hf["q_capped"] = hf["q"].clip(upper=q95)\n'
    'print(f"95th percentile cap: {q95:.1f} mW/m2")\n'
    'print(f"After cap - max: {hf[\'q_capped\'].max():.1f}, mean: {hf[\'q_capped\'].mean():.1f}")',
    'nb5_0005'
))

# Cell 4: IDW interpolation
cells.append(md(
    '## 3. IDW Interpolation to Grid\n'
    '\n'
    'Inverse distance weighting (power=2, k=8 nearest neighbors) '
    'interpolates measured heat flow to each of the 974 grid cell centroids.',
    'nb5_0006'
))

cells.append(code(
    '# Convert heat flow points to EPSG:32610\n'
    'hf_gdf = gpd.GeoDataFrame(\n'
    '    hf,\n'
    '    geometry=gpd.points_from_xy(hf.lon, hf.lat),\n'
    '    crs="EPSG:4326"\n'
    ').to_crs("EPSG:32610")\n'
    '\n'
    'src_coords = np.column_stack([hf_gdf.geometry.x, hf_gdf.geometry.y])\n'
    'src_q      = hf_gdf["q_capped"].values\n'
    '\n'
    'tree = cKDTree(src_coords)\n'
    'K, POWER = 8, 2\n'
    'dists, idxs = tree.query(grid_coords, k=K)\n'
    '\n'
    '# IDW: weight = 1/d^2; handle exact coincidences\n'
    'eps = 1e-6\n'
    'dists = np.where(dists < eps, eps, dists)\n'
    'weights = 1.0 / (dists ** POWER)\n'
    'weights /= weights.sum(axis=1, keepdims=True)\n'
    'q_interp = (weights * src_q[idxs]).sum(axis=1)\n'
    '\n'
    'grid["geothermal_score"] = q_interp / q_interp.max()\n'
    'print(f"geothermal_score: {grid.geothermal_score.min():.3f} - {grid.geothermal_score.max():.3f}")\n'
    'print(f"  median: {grid.geothermal_score.median():.3f}")',
    'nb5_0007'
))

# Cell 5: map
cells.append(md('## 4. Map', 'nb5_0008'))

cells.append(code(
    'fig, ax = plt.subplots(1, 1, figsize=(12, 10), facecolor=DARK_BG)\n'
    'ax.set_facecolor(DARK_BG)\n'
    'wa.boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0, zorder=1)\n'
    '\n'
    'n_before = len(fig.axes)\n'
    'grid.plot(column="geothermal_score", ax=ax, cmap="inferno", vmin=0, vmax=1,\n'
    '          legend=True,\n'
    '          legend_kwds={"shrink": 0.65, "label": "0=low / 1=high heat flow"},\n'
    '          alpha=0.85, zorder=2)\n'
    'if len(fig.axes) > n_before:\n'
    '    cb = fig.axes[-1]\n'
    '    cb.tick_params(labelsize=14, colors=WHITE)\n'
    '    cb.yaxis.label.set_color(WHITE)\n'
    '    cb.yaxis.label.set_size(14)\n'
    '\n'
    '# Scatter heat flow measurement points\n'
    'hf_gdf_plot = hf_gdf.to_crs("EPSG:32610")\n'
    'ax.scatter(hf_gdf_plot.geometry.x, hf_gdf_plot.geometry.y,\n'
    '           c=hf_gdf_plot["q_capped"], cmap="inferno",\n'
    '           s=12, alpha=0.5, zorder=3, linewidths=0)\n'
    '\n'
    '_rep  = dc_gdf[dc_gdf["source"] == "reported"]\n'
    '_prop = dc_gdf[dc_gdf["source"] == "proposed"]\n'
    'ax.scatter(_rep.geometry.x,  _rep.geometry.y,\n'
    '           c=WHITE, s=120, marker="D", zorder=5,\n'
    '           edgecolors="black", linewidths=0.8)\n'
    'ax.scatter(_prop.geometry.x, _prop.geometry.y,\n'
    '           facecolors="none", s=120, marker="D", zorder=5,\n'
    '           edgecolors="black", linewidths=1.5)\n'
    '\n'
    'ax.set_title(\n'
    '    "Washington State: Geothermal Heat Flow (IHFC GHFDB 2024)\\n"\n'
    '    "(IDW from 664 measured boreholes; capped at 95th pct = 162 mW/m2)\\n"\n'
    '    "White filled = existing DC  /  outline = proposed DC",\n'
    '    color=WHITE, fontsize=18, pad=10, linespacing=1.4\n'
    ')\n'
    'ax.set_xlabel(""); ax.set_ylabel("")\n'
    'ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)\n'
    'for spine in ax.spines.values():\n'
    '    spine.set_edgecolor("#4a4a6a")\n'
    '\n'
    'plt.tight_layout()\n'
    'plt.savefig(PROCESSED / "geothermal.png", dpi=150,\n'
    '            bbox_inches="tight", facecolor=fig.get_facecolor())\n'
    'plt.show()\n'
    'print("Saved to data/processed/geothermal.png")',
    'nb5_0009'
))

# Cell 6: export
cells.append(md('## 5. Export updated grid_scores.geojson', 'nb5_0010'))

cells.append(code(
    'grid_out = grid.drop(columns=["centroid"]).to_crs("EPSG:4326")\n'
    'grid_out.to_file("static/grid_scores.geojson", driver="GeoJSON")\n'
    'print(f"Saved static/grid_scores.geojson")\n'
    'print(f"Columns: {list(grid_out.columns)}")',
    'nb5_0011'
))

# Cell 7: findings
cells.append(md('## 6. Key Findings', 'nb5_0012'))

cells.append(code(
    'print("=== Proposed Sites ===")\n'
    'for _, row in dc_gdf[dc_gdf["source"] == "proposed"].iterrows():\n'
    '    pt = row.geometry\n'
    '    dists = grid.centroid.apply(lambda c: pt.distance(c))\n'
    '    n = grid.loc[dists.idxmin()]\n'
    '    q_val = n.geothermal_score * hf["q_capped"].max()\n'
    '    print(f\'  {row["name"]}:\\n\'\n'
    '          f\'    geothermal_score={n.geothermal_score:.3f}  \'\n'
    '          f\'(~{q_val:.0f} mW/m2 interpolated)\\n\')\n'
    '\n'
    'print("=== Existing Clusters (unique cells) ===")\n'
    'seen = set()\n'
    'for _, row in dc_gdf[dc_gdf["source"] == "reported"].iterrows():\n'
    '    pt = row.geometry\n'
    '    dists = grid.centroid.apply(lambda c: pt.distance(c))\n'
    '    n = grid.loc[dists.idxmin()]\n'
    '    key = round(n.geothermal_score, 3)\n'
    '    if key not in seen:\n'
    '        seen.add(key)\n'
    '        q_val = n.geothermal_score * hf["q_capped"].max()\n'
    '        print(f\'  {row["name"]}:\\n\'\n'
    '              f\'    geothermal_score={n.geothermal_score:.3f}  \'\n'
    '              f\'(~{q_val:.0f} mW/m2 interpolated)\\n\')',
    'nb5_0013'
))

nb = {
    'nbformat': 4,
    'nbformat_minor': 5,
    'metadata': {
        'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python', 'version': '3.7.6'}
    },
    'cells': cells
}

with open('05_geothermal.ipynb', 'w') as f:
    json.dump(nb, f, indent=1)
print('NB5 written: 05_geothermal.ipynb')
