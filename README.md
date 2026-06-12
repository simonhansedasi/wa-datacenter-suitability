# Data Center Siting Suitability

Geospatial siting analysis quantifying data center land suitability across US states using
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
conda activate GrapeExpectations

# State-wide atlas (fishnet grid)
python scripts/run_pipeline.py WA

# ZCTA study (ZIP Code resolution — for jurisdiction-scale studies)
python zcta/run_zcta_study.py WA
```

See [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md) for full setup, step descriptions, and troubleshooting.

## Product tiers

| Tier | Geography | URL pattern | Use case |
|---|---|---|---|
| State atlas | 0.15° fishnet (~14 km) | `/wa/` | Public map, press, Steward briefings |
| ZCTA study | ZIP Code Tabulation Areas | `/wa/study/` | Jurisdiction studies — demographic data native to ZCTA |
| City case study | Filtered ZCTA subset | `/wa/study/seattle/` | City-scoped report with policy context |

The fishnet atlas and ZCTA study use identical indicator definitions. The ZCTA advantage is
methodological: EJ burden and population exposure are native Census ZCTA data, so no spatial
join approximation is needed to assign tract-level demographics to grid cells.

## Indicators

| # | Score | Source | Type |
|---|---|---|---|
| 1 | tx_score | OSM HV transmission lines | Suitability |
| 2 | water_score | Open-Meteo ERA5 30-yr precip | Suitability |
| 3 | ej_score | Census ACS poverty + minority rate | Suitability |
| 4 | seismic_score | USGS ASCE 7-22 PGA | Risk |
| 5 | flood_score | FEMA NFHL flood zones | Risk |
| 6 | contamination_score | EPA TRI facility proximity | Environmental |
| 7 | waterway_score | OSM major rivers | Environmental |
| 8 | geothermal_score | IHFC GHFDB 2024 heat flow | Opportunity |
| 9 | flatness_score | SRTM1 terrain flatness | Hard gate |
| 10 | protected_score | Esri Federal Lands + TIGER tribal | Hard gate |

Hard gates 9 and 10 are binary exclusions applied regardless of slider weights.
All other scores are normalized 0-1 (1 = most favorable).

## Analysis grid (Washington State baseline)

**Fishnet atlas:** 974 cells, 0.15-degree (~14 km), clipped to WA boundary.
Two hard gates remove 124 cells (12.7%), leaving 850 viable candidates.

**ZCTA study:** 575 ZCTAs; median 94 km² (0.3× fishnet cell).
Urban western WA has ZCTAs as small as 2 km²; eastern WA corridor ZCTAs are ~250-800 km².

Key findings (WA fishnet):
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
```

| Script | Outputs |
|---|---|
| 01_basemap.py | state.geojson, datacenters.geojson, transmission.geojson |
| 02_indicators.py | Fishnet grid; tx_score, water_score, ej_score, pop_exposure_score |
| 03_risk.py | seismic_score, flood_score |
| 04_environment.py | contamination_score (EPA TRI), waterway_score (OSM rivers) |
| 05_geothermal.py | geothermal_score (IHFC GHFDB 2024, bbox-filtered) |
| 06_terrain.py | flatness_score (SRTM1, hard gate at 3% flat area) |
| 07_protected.py | protected_score (Esri Federal Lands + TIGER tribal, gate at 25%) |

Output: `data/{STATE}/grid_scores.geojson`

## ZCTA study pipeline

`zcta/` runs a ZIP Code Tabulation Area resolution study for any state.
Steps 03-07 from the main pipeline are reused via `DC_SUBDIR=zcta` env var.

```bash
python zcta/run_zcta_study.py WA
python zcta/run_zcta_study.py WA --start 03   # resume after step 02
```

| Script | Role |
|---|---|
| zcta/02_zcta_indicators.py | ZCTA boundaries (Census 2020); tx_score, water_score, ej_score, pop_exposure_score |
| scripts/03-07 | Reused unchanged — geometry-agnostic |

Output: `data/{STATE}/zcta/grid_scores.geojson`

ZCTA boundary source: Census 2020 500k cartographic boundaries.
No 2022/2023/2024 ZCTA boundary files exist — 2020 is the current standard.

## City case studies

City-scoped studies filter a state's ZCTA data to a defined set of ZIPs and add
policy/seismic context. Add a new city by adding an entry to `REGIONS` in `src/app.py`.

**Seattle (WA)** — live at `/wa/study/seattle/`:
- 29 city-limits ZCTAs, 0 hard-gated
- Key within-city differentiators: EJ burden (spread 0.63), terrain flatness (spread 0.76)
- Near-uniform within city: water availability (spread 0.01), seismic (spread 0.02)
- Policy context: Seattle moratorium on new data centers >20 MW (April 2026)

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
| Census ZCTA 2020 cartographic boundaries | ZCTA study tier |
| OSM Overpass API | Data centers, HV transmission, rivers |
| EIA Form 860 (2023) | Power plant locations |
| Census ACS 5-yr 2022 | Demographic burden (poverty + minority rate) |
| Open-Meteo ERA5 archive | 30-yr mean annual precipitation |
| USGS ASCE 7-22 API | Seismic hazard (PGA) |
| FEMA NFHL REST API | Special Flood Hazard Areas |
| EPA Envirofacts REST API (TRI_FACILITY) | Industrial facility proximity |
| IHFC GHFDB 2024 | Geothermal heat flow boreholes |
| NASA SRTM1 (AWS S3) | 30m digital elevation model |
| Esri USA Federal Lands | NPS, USFWS, DoD, Forest Service boundaries |
| Census TIGER AIANNH | Tribal land boundaries |
