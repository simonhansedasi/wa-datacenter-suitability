# Data Center Siting Suitability

Geospatial case study quantifying ethical data center siting across US states using
ten publicly available indicator layers and two hard buildability gates.
Live at [datacenters.simonhansedasi.com](https://datacenters.simonhansedasi.com).

## The argument

Washington's existing data center corridor (Quincy / East Wenatchee) is optimized for
one dimension — grid access — at the expense of water availability and community burden.
The Columbia Basin's water allocation is essentially fully subscribed; Grant County's own
administrator has stated that water and power are "maxed out." Meanwhile, 25 data center
projects were canceled nationally in 2025 due to community opposition, up from 6 in 2024.
This tool makes those tradeoffs visible and quantifiable.

## Quick start

```bash
conda env create -f environment.yml
conda activate datacenter_siting
python scripts/run_pipeline.py WA
```

See [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md) for full setup, step descriptions, and troubleshooting.

## Indicators

| # | Score | Source | Type |
|---|---|---|---|
| 1 | tx_score | OSM HV transmission lines | Suitability |
| 2 | water_score | Open-Meteo ERA5 30-yr precip | Suitability |
| 3 | ej_score | Census ACS poverty + minority rate | Suitability |
| 4 | seismic_score | USGS ASCE 7-22 PGA | Risk |
| 5 | flood_score | FEMA NFHL flood zones | Risk |
| 6 | contamination_score | EPA Superfund NPL sites | Environmental |
| 7 | waterway_score | OSM major rivers | Environmental |
| 8 | geothermal_score | IHFC GHFDB 2024 heat flow | Opportunity |
| 9 | flatness_score | SRTM1 terrain flatness | Hard gate |
| 10 | protected_score | Esri Federal Lands + TIGER tribal | Hard gate |

Hard gates 9 and 10 are binary exclusions applied regardless of slider weights.
All other scores are normalized 0-1 (1 = most favorable).

## Analysis grid (Washington State baseline)

974 cells, 0.15-degree fishnet (~14 km), clipped to WA boundary.
Two hard gates remove 124 cells (12.7%), leaving **850 viable candidates**.

Key findings:
- Quincy corridor: tx=0.988, water=0.189 — grid-optimal, water-constrained
- Digital Realty proposed (Cascade foothills): composite=0.783 vs Quincy=0.599
- Tri-Cities emerging cluster (Wallula Gap, Atlas Agro, Trammell Crow): water=0.000
- Tukwila/HorizonIQ: water=0.739 but ej=0.109 — worst community burden of any cluster

## Script pipeline

`scripts/` runs any US state end-to-end. All 50 states defined in `scripts/config.py`.

```bash
python scripts/run_pipeline.py WA              # full run
python scripts/run_pipeline.py OR --start 03   # resume from step 03
python scripts/run_pipeline.py TX --only 06 07 # terrain + protected only
python scripts/run_pipeline.py WA --deploy     # run + copy to static/
```

| Script | Outputs |
|---|---|
| 01_basemap.py | state.geojson, datacenters.geojson, transmission.geojson, plants |
| 02_indicators.py | Fishnet grid; tx_score, water_score, ej_score |
| 03_risk.py | seismic_score, flood_score |
| 04_environment.py | contamination_score (EPA NPL), waterway_score (OSM rivers) |
| 05_geothermal.py | geothermal_score (IHFC GHFDB 2024, bbox-filtered) |
| 06_terrain.py | flatness_score (SRTM1, hard gate at 3% flat area) |
| 07_protected.py | protected_score (Esri Federal Lands + TIGER tribal, gate at 25%) |

Output: `data/{STATE}/grid_scores.geojson`

## Notebooks

`notebooks/` contains the original exploratory notebooks for Washington State.
They share the same logic as the scripts but are cell-by-cell and WA-specific.

## Setup notes

- No GDAL required. Terrain uses `requests` + `numpy` to parse SRTM1 HGT binaries.
- Census API key required for step 02 (free at census.gov/developers).
  Set `CENSUS_API_KEY` in `~/.env` or as an environment variable.
- IHFC 2024 shapefile required for step 05. Place at `data/raw/IHFC_2024_GHFDB.shp`.
  Step 05 completes without it but sets geothermal_score = 0.5 (neutral).

## Data sources

All publicly available, no proprietary data.

| Source | Used for |
|---|---|
| Census TIGER 2022 | State boundaries, census tracts |
| OSM Overpass API | Data centers, HV transmission, rivers |
| EIA Form 860 (2023) | Power plant locations |
| Census ACS 5-yr 2022 | Demographic burden (poverty + minority rate) |
| Open-Meteo ERA5 archive | 30-yr mean annual precipitation |
| USGS ASCE 7-22 API | Seismic hazard (PGA) |
| FEMA NFHL REST API | Special Flood Hazard Areas |
| EPA Envirofacts REST API | Superfund NPL sites |
| IHFC GHFDB 2024 | Geothermal heat flow boreholes |
| NASA SRTM1 (AWS S3) | 30m digital elevation model |
| Esri USA Federal Lands | NPS, USFWS, DoD, Forest Service boundaries |
| Census TIGER AIANNH | Tribal land boundaries |
