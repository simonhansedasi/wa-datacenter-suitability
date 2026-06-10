# Washington State Data Center Siting Suitability

Geospatial case study quantifying ethical and cost-effective data center siting in Washington
State using ten publicly available indicator layers plus two hard buildability gates. Live at
[datacenters.simonhansedasi.com](https://datacenters.simonhansedasi.com).

## The argument
Washington's existing data center corridor (Quincy / East Wenatchee) is optimized for one
dimension — grid access — at the expense of water availability and community burden. The
Columbia Basin's water allocation is essentially fully subscribed; Grant County's own
administrator has stated that water and power are "maxed out." Meanwhile, 25 data center
projects were canceled nationally in 2025 due to community opposition, up from 6 in 2024.
This tool makes those tradeoffs visible and quantifiable.

## Notebooks

### 01_basemap.ipynb
Basemap: WA boundary, data center locations (OSM + curated, 15 operating + 4 proposed),
high-voltage transmission lines (OSM ≥100kV), EIA Form 860 power plant locations.

### 02_stress_indicators.ipynb
Three core suitability indicators:
- **Transmission proximity** — distance to nearest HV line (OSM)
- **Water availability** — 30-yr mean annual precipitation, ERA5 via Open-Meteo
- **Community burden** — Census ACS Demographic Index (poverty + minority rate, replicating EPA EJScreen)

### 03_risk_modifiers.ipynb
Risk-side indicators:
- **Seismic safety** — PGA at 2% probability in 50 years (USGS ASCE 7-22 API)
- **Flood safety** — binary SFHA exclusion (FEMA NFHL REST API)

### 04_environmental_risk.ipynb
- **Contamination proximity** — distance to nearest EPA Superfund NPL site (26 WA sites)
- **Waterway sensitivity** — proximity to major regulated waterways as ESA/thermal discharge proxy

### 05_geothermal.ipynb
- **Geothermal opportunity** — surface heat flow from IHFC GHFDB 2024 (664 WA boreholes, IDW interpolation, capped at 95th pct to suppress Mt Baker anomaly)

### 06_terrain.ipynb
- **Terrain flatness** — fraction of ~90m SRTM1 pixels with slope < 5° per grid cell
- Hard gate: cells with < 3% flat area (< ~185 acres) receive flatness_score = 0 and are excluded entirely
- 61 cells gated (6.3%); Quincy = 0.769, Columbia Basin proposed sites = 1.000

### 07_protected_land.ipynb
- **Protected land gate** — overlap with NPS, USFWS, DoD, Forest Service (Esri Federal Lands) + Census TIGER tribal boundaries
- Hard gate: cells with > 25% protected overlap receive protected_score = 0 and are excluded entirely
- 82 cells gated (8.4%); all existing and proposed cluster cells pass

## Analysis grid
974 cells, 0.15-degree fishnet (~14 km), clipped to WA boundary. Two hard gates remove
124 cells (12.7%), leaving **850 viable candidates** for composite scoring.

## Setup

```bash
conda env create -f environment.yml
./setup_env.sh   # creates conda env + registers Jupyter kernel
```

No GDAL required. Terrain data uses `requests` + `numpy` to parse SRTM1 HGT binary tiles
directly. All other spatial work uses `geopandas`.

Census API key required for NB02 (free at census.gov/developers). Code reads from
`/home/simonhans/coding/snotrac/.env` as `CENSUS_API_KEY=<key>`.

## Data sources
All publicly available, no proprietary data. See `CONTEXT.md` in
`~/coding/contexts/datacenter_siting/` for full source table and caching details.
