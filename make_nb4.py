"""Build 04_environmental_risk.ipynb programmatically."""
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

# ── Cell 0: title ─────────────────────────────────────────────────────
cells.append(md(
    '# Notebook 4: Environmental Risk\n'
    '\n'
    'Adds two environmental risk modifiers:\n'
    '- **Contamination proximity**: distance to nearest EPA Superfund NPL site in WA\n'
    '- **Waterway sensitivity**: proximity to major regulated rivers (Columbia, Snake, Spokane, Skagit, Yakima)\n'
    '  as a proxy for ESA thermal discharge risk and water withdrawal scrutiny.\n'
    '\n'
    '| Layer | Source |\n'
    '|---|---|\n'
    '| Superfund NPL sites | EPA NPL State List (hardcoded ~26 active WA sites) |\n'
    '| Major waterways | Sample points along key WA rivers, IDW to grid |\n'
    '| Grid | static/grid_scores.geojson (NB3 output, 974 cells) |',
    'nb4_0000'
))

# ── Cell 1: imports ────────────────────────────────────────────────────
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
    'nb4_0001'
))

# ── Cell 2: load grid ──────────────────────────────────────────────────
cells.append(md('## 1. Load grid and boundaries', 'nb4_0002'))

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
    'print(f"Columns: {list(grid.columns)}")',
    'nb4_0003'
))

# ── Cell 3: NPL sites ──────────────────────────────────────────────────
cells.append(md(
    '## 2. Contamination Proximity\n'
    '\n'
    'Sites from [EPA NPL State List for Washington]'
    '(https://www.epa.gov/superfund/national-priorities-list-npl-sites-state).\n'
    'Coordinates are approximate site centroids.',
    'nb4_0004'
))

cells.append(code(
    '# Active WA Superfund NPL sites\n'
    '# Source: EPA https://www.epa.gov/superfund/national-priorities-list-npl-sites-state\n'
    'wa_npl = [\n'
    '    # Eastern WA\n'
    '    {"name": "Hanford Site",                         "lat": 46.5507, "lon": -119.5279},\n'
    '    {"name": "Pasco Sanitary Landfill",              "lat": 46.2395, "lon": -119.0811},\n'
    '    {"name": "Yakima Plating",                       "lat": 46.6100, "lon": -120.5105},\n'
    '    {"name": "Holden Mine",                          "lat": 48.2255, "lon": -120.7370},\n'
    '    {"name": "Spokane Junkyard",                     "lat": 47.6614, "lon": -117.4329},\n'
    '    {"name": "Inland Empire Refining",               "lat": 47.5814, "lon": -117.4414},\n'
    '    # Seattle / King County\n'
    '    {"name": "Lower Duwamish Waterway",              "lat": 47.5497, "lon": -122.3318},\n'
    '    {"name": "Harbor Island Lead",                   "lat": 47.5795, "lon": -122.3382},\n'
    '    {"name": "Pacific Sound Resources",              "lat": 47.4888, "lon": -122.3264},\n'
    '    {"name": "Western Processing",                   "lat": 47.3876, "lon": -122.1835},\n'
    '    {"name": "Greenacres Landfill",                  "lat": 47.3615, "lon": -122.1071},\n'
    '    {"name": "Oeser Company",                        "lat": 47.9278, "lon": -122.2259},\n'
    '    {"name": "Lockheed West Seattle",                "lat": 47.5560, "lon": -122.3800},\n'
    '    {"name": "Silver Lake",                          "lat": 47.8612, "lon": -122.1984},\n'
    '    {"name": "Cleaver-Brooks",                       "lat": 47.9456, "lon": -122.1989},\n'
    '    # Tacoma / Pierce County\n'
    '    {"name": "Commencement Bay-Nearshore/Tideflats", "lat": 47.2695, "lon": -122.4111},\n'
    '    {"name": "American Lake Gardens",                "lat": 47.1698, "lon": -122.3972},\n'
    '    {"name": "Tacoma Smelter Plume",                 "lat": 47.2895, "lon": -122.4298},\n'
    '    {"name": "McChord Air Force Base",               "lat": 47.1368, "lon": -122.4761},\n'
    '    {"name": "Fort Lewis (JBLM)",                    "lat": 47.0836, "lon": -122.5791},\n'
    '    # Kitsap / West Sound\n'
    '    {"name": "Wyckoff/Eagle Harbor",                 "lat": 47.6227, "lon": -122.5107},\n'
    '    {"name": "Bangor Naval Sub Base",                "lat": 47.6979, "lon": -122.7367},\n'
    '    # North Puget Sound\n'
    '    {"name": "Tulalip Landfill",                     "lat": 48.0498, "lon": -122.2696},\n'
    '    {"name": "Smokey Point Motor Speedway",          "lat": 48.1773, "lon": -122.1746},\n'
    '    # SW Washington\n'
    '    {"name": "Frontier Hard Chrome (Vancouver WA)",  "lat": 45.6352, "lon": -122.5985},\n'
    '    {"name": "E.I. Du Pont (Tacoma)",                "lat": 47.2200, "lon": -122.4500},\n'
    ']\n'
    '\n'
    'npl_gdf = gpd.GeoDataFrame(\n'
    '    wa_npl,\n'
    '    geometry=gpd.points_from_xy([s["lon"] for s in wa_npl], [s["lat"] for s in wa_npl]),\n'
    '    crs="EPSG:4326"\n'
    ').to_crs("EPSG:32610")\n'
    '\n'
    'npl_coords = np.column_stack([npl_gdf.geometry.x, npl_gdf.geometry.y])\n'
    'tree_npl = cKDTree(npl_coords)\n'
    'dist_npl, _ = tree_npl.query(grid_coords, k=1)\n'
    '\n'
    'grid["contamination_score"] = dist_npl / dist_npl.max()\n'
    'print(f"contamination_score: {grid.contamination_score.min():.3f} - {grid.contamination_score.max():.3f}")',
    'nb4_0005'
))

# ── Cell 4: waterways ──────────────────────────────────────────────────
cells.append(md(
    '## 3. Waterway Sensitivity\n'
    '\n'
    'Sample points along the Columbia, Snake, Spokane, Skagit, and Yakima rivers.\n'
    'Proximity is a proxy for ESA Section 7 thermal discharge constraints\n'
    'and water withdrawal regulatory scrutiny.\n'
    'Closer = higher regulatory risk = lower score.',
    'nb4_0006'
))

cells.append(code(
    '# Sample points along major WA regulated waterways\n'
    'columbia_pts = [\n'
    '    (48.98,-117.63),(48.60,-118.10),(48.30,-118.45),(47.95,-118.85),\n'
    '    (47.75,-119.15),(47.55,-119.45),(47.30,-119.65),(47.10,-119.65),\n'
    '    (46.70,-119.60),(46.45,-119.40),(46.30,-119.15),(46.20,-119.00),\n'
    '    (46.10,-118.97),(45.95,-119.48),(45.85,-119.85),(45.75,-120.40),\n'
    '    (45.70,-121.00),(45.65,-121.60),(45.62,-122.20),(45.60,-122.75),\n'
    ']\n'
    'snake_pts = [\n'
    '    (46.40,-117.05),(46.35,-117.45),(46.30,-118.00),\n'
    '    (46.28,-118.50),(46.24,-119.05),\n'
    ']\n'
    'spokane_pts = [\n'
    '    (47.66,-117.42),(47.68,-117.80),(47.72,-118.10),(47.78,-118.40),\n'
    ']\n'
    'skagit_pts = [\n'
    '    (48.72,-121.20),(48.65,-121.60),(48.55,-121.90),\n'
    '    (48.45,-122.10),(48.40,-122.25),(48.47,-122.40),\n'
    ']\n'
    'yakima_pts = [\n'
    '    (46.61,-120.51),(46.42,-120.12),(46.28,-119.87),(46.22,-119.62),\n'
    ']\n'
    '\n'
    'all_pts = columbia_pts + snake_pts + spokane_pts + skagit_pts + yakima_pts\n'
    'riv_df  = pd.DataFrame(all_pts, columns=["lat","lon"])\n'
    'riv_gdf = gpd.GeoDataFrame(\n'
    '    riv_df,\n'
    '    geometry=gpd.points_from_xy(riv_df.lon, riv_df.lat),\n'
    '    crs="EPSG:4326"\n'
    ').to_crs("EPSG:32610")\n'
    '\n'
    'riv_coords = np.column_stack([riv_gdf.geometry.x, riv_gdf.geometry.y])\n'
    'tree_riv = cKDTree(riv_coords)\n'
    'dist_riv, _ = tree_riv.query(grid_coords, k=1)\n'
    '\n'
    'grid["waterway_score"] = dist_riv / dist_riv.max()\n'
    'print(f"waterway_score: {grid.waterway_score.min():.3f} - {grid.waterway_score.max():.3f}")',
    'nb4_0007'
))

# ── Cell 5: maps ───────────────────────────────────────────────────────
cells.append(md('## 4. Maps', 'nb4_0008'))

cells.append(code(
    'layers = [\n'
    '    ("contamination_score", "Contamination Proximity",\n'
    '     "(1 = far from Superfund NPL site)"),\n'
    '    ("waterway_score",       "Waterway Sensitivity",\n'
    '     "(1 = far from major regulated river)"),\n'
    ']\n'
    '\n'
    'fig, axes = plt.subplots(1, 2, figsize=(20, 9), facecolor=DARK_BG)\n'
    '\n'
    'for ax, (col, title, subtitle) in zip(axes, layers):\n'
    '    ax.set_facecolor(DARK_BG)\n'
    '    wa.boundary.plot(ax=ax, color="#4a4a6a", linewidth=1.0, zorder=1)\n'
    '    n_before = len(fig.axes)\n'
    '    grid.plot(column=col, ax=ax, cmap="RdYlGn", vmin=0, vmax=1,\n'
    '              legend=True,\n'
    '              legend_kwds={"shrink": 0.65, "label": "0=poor / 1=ideal"},\n'
    '              alpha=0.85, zorder=2)\n'
    '    if len(fig.axes) > n_before:\n'
    '        cb = fig.axes[-1]\n'
    '        cb.tick_params(labelsize=14, colors=WHITE)\n'
    '        cb.yaxis.label.set_color(WHITE)\n'
    '        cb.yaxis.label.set_size(14)\n'
    '    _rep  = dc_gdf[dc_gdf["source"] == "reported"]\n'
    '    _prop = dc_gdf[dc_gdf["source"] == "proposed"]\n'
    '    ax.scatter(_rep.geometry.x,  _rep.geometry.y,\n'
    '               c=WHITE, s=120, marker="D", zorder=5,\n'
    '               edgecolors="black", linewidths=0.8)\n'
    '    ax.scatter(_prop.geometry.x, _prop.geometry.y,\n'
    '               facecolors="none", s=120, marker="D", zorder=5,\n'
    '               edgecolors="black", linewidths=1.5)\n'
    '    ax.set_title(f"{title}\\n{subtitle}", color=WHITE, fontsize=20,\n'
    '                 pad=10, linespacing=1.4)\n'
    '    ax.set_xlabel(""); ax.set_ylabel("")\n'
    '    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)\n'
    '    for spine in ax.spines.values():\n'
    '        spine.set_edgecolor("#4a4a6a")\n'
    '\n'
    'plt.suptitle(\n'
    '    "Washington State: Environmental Risk Modifiers\\n"\n'
    '    "White filled = existing DC  /  outline = proposed DC",\n'
    '    color=WHITE, fontsize=22, y=0.90\n'
    ')\n'
    'plt.tight_layout(rect=[0, 0, 1, 0.86])\n'
    'plt.savefig(PROCESSED / "environmental_risk.png", dpi=150,\n'
    '            bbox_inches="tight", facecolor=fig.get_facecolor())\n'
    'plt.show()\n'
    'print("Saved to data/processed/environmental_risk.png")',
    'nb4_0009'
))

# ── Cell 6: export ─────────────────────────────────────────────────────
cells.append(md('## 5. Export updated grid_scores.geojson', 'nb4_0010'))

cells.append(code(
    'grid_out = grid.drop(columns=["centroid"]).to_crs("EPSG:4326")\n'
    'grid_out.to_file("static/grid_scores.geojson", driver="GeoJSON")\n'
    'print(f"Saved static/grid_scores.geojson")\n'
    'print(f"Columns: {list(grid_out.columns)}")',
    'nb4_0011'
))

# ── Cell 7: findings ───────────────────────────────────────────────────
cells.append(md('## 6. Key Findings', 'nb4_0012'))

cells.append(code(
    'print("=== Proposed Sites ===")\n'
    'for _, row in dc_gdf[dc_gdf["source"] == "proposed"].iterrows():\n'
    '    pt = row.geometry\n'
    '    dists = grid.centroid.apply(lambda c: pt.distance(c))\n'
    '    n = grid.loc[dists.idxmin()]\n'
    '    print(f\'  {row["name"]}:\\n\'\n'
    '          f\'    contamination={n.contamination_score:.3f}\'\n'
    '          f\'  waterway={n.waterway_score:.3f}\\n\')\n'
    '\n'
    'print("=== Existing Clusters ===")\n'
    'seen = set()\n'
    'for _, row in dc_gdf[dc_gdf["source"] == "reported"].iterrows():\n'
    '    pt = row.geometry\n'
    '    dists = grid.centroid.apply(lambda c: pt.distance(c))\n'
    '    n = grid.loc[dists.idxmin()]\n'
    '    key = (round(n.contamination_score,2), round(n.waterway_score,2))\n'
    '    if key not in seen:\n'
    '        seen.add(key)\n'
    '        print(f\'  {row["name"]}:\\n\'\n'
    '              f\'    contamination={n.contamination_score:.3f}\'\n'
    '              f\'  waterway={n.waterway_score:.3f}\\n\')',
    'nb4_0013'
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

with open('04_environmental_risk.ipynb', 'w') as f:
    json.dump(nb, f, indent=1)
print('NB4 written: 04_environmental_risk.ipynb')
