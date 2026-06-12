# Data Center Siting Pipeline — Instructions

This guide covers running the `scripts/` pipeline to produce a siting suitability audit
for any US state. The pipeline downloads all data from public APIs, scores a 0.15-degree
fishnet grid on 10 indicators, applies two hard buildability gates, and writes
`grid_scores.geojson` as the output artifact.

---

## Prerequisites

### 1. Python environment

```bash
conda env create -f environment.yml
conda activate datacenter_siting
```

No GDAL is required. The environment uses geopandas, numpy, scipy, requests, and
matplotlib only.

### 2. Census API key (required for step 02)

The demographic burden score pulls Census ACS data. Get a free key at
[census.gov/developers](https://api.census.gov/data/key_signup.html) and add it to
your environment:

```bash
# Option A: add to your ~/.env or any .env file the script will find
echo "CENSUS_API_KEY=your_key_here" >> ~/.env

# Option B: set it inline when running
CENSUS_API_KEY=your_key_here python scripts/run_pipeline.py WA
```

The script also reads from `/home/simonhans/coding/snotrac/.env` automatically.

### 3. IHFC heat flow shapefile (required for step 05)

The geothermal score uses the IHFC Global Heat Flow Database 2024. The global shapefile
must be placed manually at:

```
data/raw/IHFC_2024_GHFDB.shp   (+ .dbf, .prj, .shx, .cpg, .qmd)
```

Download from [ihfc-iugg.org](https://ihfc-iugg.org/products/global-heat-flow-database)
or the IHFC data portal. Note: the `.dbf` companion file is ~1.4 GB — it is not committed
to this repository and must be downloaded separately.

The pipeline will filter it to your target state's bounding box and cache the result in
`data/{STATE}/raw/heatflow.csv`. If the shapefile is missing, step 05 still runs but
sets `geothermal_score = 0.5` for all cells and prints a warning.

---

## Running the pipeline

All commands are run from the project root (`~/coding/datacenter_siting/`).

### Full run

```bash
python scripts/run_pipeline.py WA
```

This runs all 7 steps in sequence. First run for a new state takes 30–90 minutes
depending on state size and API response times. Subsequent runs are faster because
all raw data is cached.

### Resume after a failure

If a step fails, fix the issue and resume from that step without re-running the
earlier ones:

```bash
python scripts/run_pipeline.py WA --start 04
```

### Run only specific steps

```bash
python scripts/run_pipeline.py WA --only 06 07
```

### Deploy to the web app

After a successful run, rsync the state data to the DO server (see "Deploying a state
audit" section below). The Flask app reads `data/{STATE}/grid_scores.geojson` directly —
no `static/` copy is needed.

---

## Output structure

```
data/{STATE}/
    raw/
        state.geojson           — Census TIGER state boundary
        datacenters.geojson     — OSM data centers
        transmission.geojson    — OSM HV transmission lines (>=100kV)
        eia860_plants.geojson   — EIA Form 860 power plants
        acs_demog.csv           — Census ACS demographics (step 02)
        tracts.geojson          — Census TIGER tract boundaries (step 02)
        precip_coarse.csv       — Open-Meteo ERA5 precip sample points (step 02)
        seismic_sample.csv      — USGS ASCE 7-22 sample points (step 03)
        sfha.geojson            — FEMA NFHL flood zones (step 03)
        tri_facilities.csv      — EPA TRI facility locations (step 04)
        rivers.geojson          — OSM major rivers (step 04)
        heatflow.csv            — IHFC boreholes filtered to bbox (step 05)
        srtm_tiles/             — SRTM1 HGT elevation tiles (step 06)
        federal_lands.geojson   — Esri Federal Lands (step 07)
        tribal_tiger.geojson    — TIGER AIANNH tribal areas (step 07)
    processed/
        basemap.png
        indicators.png
        risk_modifiers.png
        environmental_risk.png
        geothermal.png
        terrain_flatness.png
        protected_land.png
    grid_scores.geojson         — Final scored grid (all 10 columns)
```

All raw files are cached. Re-running a step will use the cached version and skip
downloads. To force a re-download, delete the relevant file and re-run.

### grid_scores.geojson columns

| Column | Type | Description |
|---|---|---|
| cell_id | int | Grid cell index |
| tx_score | 0-1 | Proximity to HV transmission (1 = adjacent) |
| water_score | 0-1 | Annual precipitation (1 = highest) |
| ej_score | 0-1 | 1 - demographic burden (1 = least burdened) |
| seismic_score | 0-1 | 1 - peak ground acceleration (1 = lowest risk) |
| flood_score | 0-1 | 1.0 outside SFHA, 0.0 inside |
| contamination_score | 0-1 | Distance to nearest NPL site (1 = farthest) |
| waterway_score | 0-1 | Distance to nearest major river (1 = farthest) |
| geothermal_score | 0-1 | Heat flow (1 = highest) |
| flatness_score | 0 or 0-1 | Terrain flatness (0 = hard gated) |
| protected_score | 0 or 1 | 0 if >25% protected land, else 1 |

---

## Step-by-step details

### Step 01 — Basemap

Downloads: Census TIGER state boundary, OSM data centers, OSM HV transmission lines,
EIA Form 860 power plants.

- The OSM queries use the Overpass API. For large states (TX, CA) these queries can
  take 60-90 seconds. No credentials needed.
- EIA 860 downloads the national archive (~30 MB zip), extracts plant and generator
  sheets, and filters to the target state. Cached after first run.

### Step 02 — Stress indicators

Builds the 0.15-degree fishnet grid and computes three scores.

- **tx_score**: distance from each cell centroid to the nearest HV transmission line.
  Requires transmission.geojson from step 01.
- **water_score**: IDW from ~50 Open-Meteo ERA5 precip sample points (1991-2020 daily
  mean). Cached in precip_coarse.csv after first run. The Open-Meteo free tier has no
  key requirement but has a modest rate limit; the 0.05s sleep between calls handles it.
- **ej_score**: 1 - Census ACS demographic index (mean of poverty rate + minority rate
  per tract). Requires a Census API key.

### Step 03 — Risk modifiers

- **seismic_score**: IDW from ~50 USGS ASCE 7-22 sample points (PGA at 2% in 50yr,
  site class C). Each API call takes 1-3 seconds; the full grid of samples runs in
  ~2-5 minutes. Cached in seismic_sample.csv after first run.
- **flood_score**: binary gate from FEMA NFHL. The state bbox is divided into a 40-tile
  grid to avoid oversized API responses. Some tiles may return 0 features (no flood
  zones in that tile) — that is normal. Cached in sfha.geojson after first run.

### Step 04 — Environmental risk

- **contamination_score**: fetches EPA TRI (Toxic Release Inventory) facility locations
  from the Envirofacts `TRI_FACILITY` endpoint, then computes distance from each cell
  centroid to the nearest facility. If the API returns no results, score defaults to 1.0
  (neutral) with a warning.
- **waterway_score**: fetches major rivers (waterway=river) from OSM Overpass for the
  state bbox, then computes distance from each centroid to the nearest river segment.
  If OSM returns nothing, score defaults to 1.0 (neutral) with a warning.

### Step 05 — Geothermal

Filters the global IHFC 2024 shapefile to the state bbox, caps heat flow at the 95th
percentile to suppress hydrothermal outliers, then IDW-interpolates to grid centroids.

- Requires `data/raw/IHFC_2024_GHFDB.shp`. The global file is read once and the
  state-filtered CSV is cached.
- For states with very sparse borehole coverage, the IDW will interpolate over large
  distances and scores will be smooth/flat. This is expected.

### Step 06 — Terrain flatness

Downloads SRTM1 HGT tiles (~25 MB each) from the AWS public S3 bucket, stacks them
into a full-state DEM, downsamples 3x (30m -> ~90m), and computes slope with
`numpy.gradient`. The fraction of pixels per cell with slope < 5 degrees is the
flatness measure. Hard gate: cells with flat_frac < 3% receive flatness_score = 0.

- Tiles are cached in `raw/srtm_tiles/` after first download.
- First run downloads all tiles. WA = 45 tiles (~1.1 GB download, ~30 min first run).
  TX = 168 tiles; CA = 121 tiles.
- DEM is assembled in memory before downsampling. For large states this can use 2-9 GB
  RAM. See troubleshooting if this is a problem.

### Step 07 — Protected land

Fetches protected areas from two sources and computes the overlap fraction per cell.
Hard gate: cells with > 25% overlap receive protected_score = 0.

- **Esri Federal Lands**: NPS, USFWS, DoD, Forest Service. BLM is excluded (BLM land
  is generally leasable for development). Paginated in batches of 1000.
- **TIGER AIANNH**: Census tribal areas for the state bbox.
- The intersection step (`gpd.overlay`) can take several minutes for states with
  complex protected area boundaries (MT, WY, AZ, NM).

---

## Troubleshooting

### Census API key not found

```
RuntimeError: Census API key not found.
```

Set `CENSUS_API_KEY=your_key_here` in `~/.env`, or prefix the command:
```bash
CENSUS_API_KEY=abc123 python scripts/run_pipeline.py WA --start 02
```

---

### OSM Overpass timeout (steps 01, 04)

```
requests.exceptions.ReadTimeout
```

The Overpass API sometimes times out under heavy load. Re-run the step — if the raw
file does not exist yet, it will retry the download. If it partially created a file,
delete it first:

```bash
rm data/WA/raw/transmission.geojson   # or rivers.geojson
python scripts/run_pipeline.py WA --only 01
```

For very large states (TX, CA), the transmission query can return tens of thousands of
features. If it consistently times out, the Overpass query timeout is set to 150s in
the script. You can increase it in `01_basemap.py` → `fetch_osm_transmission`.

---

### SRTM tile 404 (step 06)

```
requests.exceptions.HTTPError: 404 Client Error
```

Some SRTM tiles don't exist (ocean tiles, uninhabited islands, tiles at the edge of
coverage). The script catches this and fills the tile with NaN. Slope over NaN areas
will also be NaN and those pixels are excluded from the flatness calculation. This is
expected behavior for coastal states.

---

### Out of memory during DEM assembly (step 06)

Step 06 assembles the full DEM in RAM before downsampling. For large states:

| State | Tiles | Approx. RAM before downsample |
|---|---|---|
| WA | 45 | ~2.3 GB |
| CA | 121 | ~6.3 GB |
| TX | 168 | ~8.7 GB |

If you hit an OOM kill, increase the downsample factor in `scripts/06_terrain.py`:

```python
DOWNSAMPLE = 6   # 30m -> ~180m; reduces RAM ~4x
```

This reduces slope precision but is generally fine for 0.15-degree grid cells (~14 km).

---

### FEMA API returns empty (step 03)

Some states have few or no SFHA polygons in certain tiles — this is normal. If the
entire state returns empty (rare), `flood_score` defaults to 1.0 for all cells and
a WARNING is printed. This means the FEMA NFHL service may be temporarily down; delete
`data/{STATE}/raw/sfha.geojson` and retry later.

---

### EPA TRI API returns no data (step 04)

```
WARNING: No TRI facility data for {STATE}; contamination_score will be uniform 1.0
```

The EPA Envirofacts `TRI_FACILITY` endpoint is sometimes unavailable or returns 0
results. Two options:

1. Delete `data/{STATE}/raw/tri_facilities.csv` and re-run step 04 to retry the API.
2. Provide a manual CSV: create `data/{STATE}/raw/tri_facilities.csv` with columns
   `lat`, `lon`, `name` and re-run step 04.

---

### IHFC shapefile missing (step 05)

```
WARNING: IHFC_2024_GHFDB.shp not found at data/raw/IHFC_2024_GHFDB.shp
geothermal_score will be uniform 0.5 (neutral)
```

Step 05 still completes with a neutral score. To get real geothermal data, place
`IHFC_2024_GHFDB.shp` (and companion `.dbf`, `.prj`, `.shx` files) at
`data/raw/IHFC_2024_GHFDB.shp`, then re-run:

```bash
rm data/{STATE}/raw/heatflow.csv   # clear cached empty file
python scripts/run_pipeline.py {STATE} --only 05
```

---

### Step fails mid-run and leaves a partial file

The scripts don't write output until the end of each step. If a step crashes before
the final `grid.to_file(grid_path)` call, `grid_scores.geojson` will still reflect
the state from the previous step. Re-running `--start NN` from the failed step is safe.

If a raw download file was partially written (e.g. a tile download crashed), delete it:

```bash
rm data/WA/raw/srtm_tiles/N48W122.hgt
python scripts/run_pipeline.py WA --only 06
```

---

### Slow Esri federal lands fetch (step 07)

The Esri paginated query fetches records in batches of 1000. States with large amounts
of federal land (AK, UT, NV, ID) may require 5-10 minutes. The script prints progress
every 1000 features. This is normal; the result is cached in `federal_lands.geojson`.

---

### Wrong UTM zone for a state

`scripts/config.py` auto-computes the UTM zone from the center longitude. For states
that span multiple zones (TN, AK, ID), the auto-computed zone may not be ideal. This
affects the accuracy of metric distance calculations (TX distance, contamination distance,
protected land area) by a few percent at most. To override for a specific state, edit
`config.py` and add `"utm_epsg": "EPSG:XXXXX"` manually to that state's entry.

---

### Re-running after upstream data has changed

All raw files are treated as permanent cache. To force a fresh download of any layer,
delete the corresponding file and re-run from that step:

```bash
# Force re-download of transmission lines
rm data/OR/raw/transmission.geojson
python scripts/run_pipeline.py OR --only 01

# Force fresh Census ACS data
rm data/OR/raw/acs_demog.csv data/OR/raw/tracts.geojson
python scripts/run_pipeline.py OR --start 02
```

---

## Running multiple states

The pipeline is independent per state. You can run states in parallel in separate
terminals:

```bash
# Terminal 1
python scripts/run_pipeline.py OR

# Terminal 2
python scripts/run_pipeline.py ID
```

Each state writes to its own `data/{STATE}/` directory and does not interfere with
other runs. The shared global files (`data/raw/IHFC_2024_GHFDB.shp`) are read-only
and safe to share.

---

## Deploying a state audit to the web app

The Flask web app at `datacenters.simonhansedasi.com` uses path-based routing.
Each state gets its own URL: `datacenters.simonhansedasi.com/wa/`, `/or/`, etc.
Flask reads `data/{STATE}/grid_scores.geojson` directly — no `static/` copy needed.

To publish a completed state run to the live site:

```bash
# Step 1: deploy code changes if needed
bash deploy_do.sh

# Step 2: rsync the state data to DO (skip srtm_tiles — not needed for serving)
rsync -av --exclude='srtm_tiles/' \
  data/WA/ \
  root@<DO_IP>:/home/simonhans/coding/datacenter_siting/data/WA/

# Step 3: if data/WA/ didn't exist on DO, create it first:
ssh root@<DO_IP> "mkdir -p /path/to/datacenter_siting/data/WA/raw /path/to/datacenter_siting/data/WA/processed"

# Step 4: restart if needed
ssh root@<DO_IP> "systemctl restart datacenter_siting"
```

The `--deploy` flag in `run_pipeline.py` prints the rsync reminder.

Note: the cluster table and written analysis in the page are still Washington-specific.
The map, sliders, and top-sites table all work correctly for any state.
