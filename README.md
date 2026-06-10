# Washington State Data Center Siting Suitability

Geospatial case study quantifying ethical and cost-effective data center siting in Washington
State using three publicly available indicator layers. Built as a portfolio piece demonstrating
multi-criteria suitability analysis with real policy context.

## The argument
Washington's existing data center corridor (Quincy / East Wenatchee) is optimized for one
dimension — grid access — at the expense of water availability and community burden. The
Columbia Basin's water allocation is essentially fully subscribed; Grant County's own
administrator has stated that water and power are "maxed out." Meanwhile, 25 data center
projects were canceled nationally in 2025 due to community opposition, up from 6 in 2024.
This tool makes those tradeoffs visible and quantifiable.

## Notebooks

### 01_basemap.ipynb
Basemap: WA boundary, known data center locations (OSM + hard-coded facilities), high-voltage
transmission lines (OSM, ≥100kV), and EIA Form 860 power plant locations by fuel type.

### 02_stress_indicators.ipynb
Three-layer composite suitability index:
- **40% Transmission Proximity** — distance to nearest HV line (OSM)
- **35% Water Availability** — 30-year mean annual precipitation, ERA5 reanalysis via Open-Meteo
- **25% Community Burden** — Census ACS Demographic Index (poverty + minority rate), replicating EPA EJScreen formula

Key result: existing Quincy cluster scores 0.599/1.0 composite; a westward site at similar
grid access but better water availability scores 0.783.

### 03_risk_modifiers.ipynb (planned)
Seismic hazard (USGS NSHM) + FEMA flood zones as risk-side modifiers.

## Setup

```bash
pip install -r requirements.txt
```

Requires a Census API key (free at census.gov/developers). Code reads from
`/home/simonhans/coding/snotrac/.env` as `CENSUS_API_KEY=<key>` or set the env var directly.

## Data sources
All publicly available. See `CONTEXT.md` in `~/coding/contexts/datacenter_siting/` for full
source table and caching details.
