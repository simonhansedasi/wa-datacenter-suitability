"""Export grid scores to static/grid_scores.geojson for the web app."""
import warnings
warnings.filterwarnings('ignore')

import json
import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path
from shapely.geometry import box, Point

RAW = Path('data/raw')
STATIC = Path('static')
STATIC.mkdir(exist_ok=True)

CRS = 'EPSG:4326'
CRS_PROJ = 'EPSG:32610'

wa     = gpd.read_file(RAW / 'wa_state.geojson')
dc_gdf = gpd.read_file(RAW / 'datacenters.geojson')
tx_gdf = gpd.read_file(RAW / 'transmission_wa.geojson')

def create_fishnet(extent_gdf, cell_size_deg=0.15):
    xmin, ymin, xmax, ymax = extent_gdf.total_bounds
    xs = np.arange(xmin, xmax + cell_size_deg, cell_size_deg)
    ys = np.arange(ymin, ymax + cell_size_deg, cell_size_deg)
    cells = [box(x, y, x + cell_size_deg, y + cell_size_deg)
             for x in xs[:-1] for y in ys[:-1]]
    grid = gpd.GeoDataFrame({'geometry': cells}, crs=CRS)
    wa_union = extent_gdf.geometry.unary_union
    grid = grid[grid.centroid.within(wa_union)].reset_index(drop=True)
    grid['cell_id'] = range(len(grid))
    return grid

def idw(src_lats, src_lons, src_vals, tgt_lats, tgt_lons, power=2):
    results = []
    for lat, lon in zip(tgt_lats, tgt_lons):
        dists = np.sqrt((src_lats - lat)**2 + (src_lons - lon)**2)
        dists = np.maximum(dists, 1e-10)
        w = 1.0 / dists**power
        results.append(float(np.sum(w * src_vals) / np.sum(w)))
    return results

print('Building fishnet...')
grid = create_fishnet(wa)

print('Transmission proximity...')
tx_proj        = tx_gdf.to_crs(CRS_PROJ)
tx_union       = tx_proj.geometry.unary_union
grid_proj      = grid.to_crs(CRS_PROJ)
centroids_proj = list(grid_proj.geometry.centroid)
grid['tx_dist_m'] = [tx_union.distance(pt) for pt in centroids_proj]
grid['tx_score']  = 1.0 - (grid['tx_dist_m'] / grid['tx_dist_m'].max())

print('EJ score...')
df     = pd.read_csv(RAW / 'acs_demog_wa.csv', dtype={'GEOID': str})
tracts = gpd.read_file(RAW / 'wa_tracts.geojson')
tracts['GEOID'] = tracts['GEOID'].astype(str).str.zfill(11)
df['GEOID']     = df['GEOID'].astype(str).str.zfill(11)
ej_gdf         = tracts[['GEOID', 'geometry']].merge(df[['GEOID', 'demog_index']], on='GEOID', how='left')
grid_pts       = gpd.GeoDataFrame({'cell_id': grid['cell_id']}, geometry=grid.geometry.centroid, crs=CRS)
joined         = gpd.sjoin(grid_pts, ej_gdf[['GEOID', 'demog_index', 'geometry']], how='left', predicate='within')
burden_by_cell = joined.groupby('cell_id')['demog_index'].mean()
grid['demog_burden'] = grid['cell_id'].map(burden_by_cell)
q01, q99 = grid['demog_burden'].quantile([0.01, 0.99])
grid['ej_score'] = 1.0 - ((grid['demog_burden'] - q01) / (q99 - q01)).clip(0, 1)
grid['ej_score'] = grid['ej_score'].fillna(grid['ej_score'].median())

print('Water score...')
precip_df = pd.read_csv(RAW / 'wa_precip_coarse.csv')
centroids = grid.geometry.centroid
tgt_lats  = np.array([p.y for p in centroids])
tgt_lons  = np.array([p.x for p in centroids])
grid['ann_precip_mm'] = idw(
    precip_df['lat'].values, precip_df['lon'].values,
    precip_df['ann_precip_mm'].values, tgt_lats, tgt_lons
)
p05, p95 = grid['ann_precip_mm'].quantile([0.05, 0.95])
grid['water_score'] = ((grid['ann_precip_mm'] - p05) / (p95 - p05)).clip(0, 1)

print('Seismic score...')
seismic_df = pd.read_csv(RAW / 'wa_seismic_sample.csv')
grid['pgam'] = idw(
    seismic_df['lat'].values, seismic_df['lon'].values,
    seismic_df['pgam'].values, tgt_lats, tgt_lons
)
p05s, p95s = grid['pgam'].quantile([0.05, 0.95])
grid['seismic_score'] = 1.0 - ((grid['pgam'] - p05s) / (p95s - p05s)).clip(0, 1)

print('Flood score...')
sfha_gdf    = gpd.read_file(RAW / 'wa_sfha.geojson')
sfha_valid  = sfha_gdf[sfha_gdf.geometry.is_valid].reset_index(drop=True)
hit         = gpd.sjoin(grid_pts, sfha_valid[['geometry']], how='left', predicate='intersects')
flooded_ids = set(hit.loc[hit['index_right'].notna(), 'cell_id'])
grid['flood_score'] = (~grid['cell_id'].isin(flooded_ids)).astype(float)

print('Exporting GeoJSON...')
score_cols = ['cell_id', 'tx_score', 'water_score', 'ej_score', 'seismic_score', 'flood_score']
export = grid[score_cols + ['geometry']].copy()
# Round scores to 3dp to reduce file size
for c in score_cols[1:]:
    export[c] = export[c].round(3)

# Simplify geometry for web (0.01 deg tolerance ~1km, fine for 14km cells)
export['geometry'] = export['geometry'].simplify(0.001)

out_path = STATIC / 'grid_scores.geojson'
export.to_file(out_path, driver='GeoJSON')

import os
print(f'Saved {len(export)} cells to {out_path} ({os.path.getsize(out_path)/1e3:.0f} KB)')

# Export datacenter locations
dc_export = dc_gdf[['name', 'operator', 'source', 'geometry']].copy()
dc_export.to_file(STATIC / 'datacenters.geojson', driver='GeoJSON')
print(f'Saved {len(dc_export)} data centers to static/datacenters.geojson')
