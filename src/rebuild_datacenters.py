"""Rebuild datacenters.geojson with expanded WA facility list from public sources."""
import geopandas as gpd
import pandas as pd
from pathlib import Path

# Sources:
#   Baxtel.com WA listings
#   datacentermap.com/usa/washington (103 facilities, 53 operators)
#   datacenters.com/locations/united-states/washington
#   WA DOR Data Center Workgroup Report Dec 2025
#   DCD / media reporting

facilities = [
    # ── Quincy / Grant County ──────────────────────────────────────────────────
    {'name': 'Microsoft Quincy Campus',       'operator': 'Microsoft',       'city': 'Quincy',        'lat': 47.234, 'lon': -119.852, 'source': 'reported'},
    {'name': 'Vantage WA13',                  'operator': 'Vantage',         'city': 'Quincy',        'lat': 47.233, 'lon': -119.847, 'source': 'reported'},
    {'name': 'CyrusOne Quincy',               'operator': 'CyrusOne',        'city': 'Quincy',        'lat': 47.236, 'lon': -119.844, 'source': 'reported'},
    {'name': 'Sabey SDC Quincy',              'operator': 'Sabey',           'city': 'Quincy',        'lat': 47.240, 'lon': -119.843, 'source': 'reported'},
    {'name': 'H5 Data Centers Quincy II',     'operator': 'H5 Data Centers', 'city': 'Quincy',        'lat': 47.232, 'lon': -119.843, 'source': 'reported'},
    {'name': 'Dell / Yahoo Quincy',           'operator': 'Dell/Yahoo',      'city': 'Quincy',        'lat': 47.236, 'lon': -119.855, 'source': 'reported'},

    # ── East Wenatchee / Malaga / Douglas County ───────────────────────────────
    {'name': 'Microsoft EAT06/EAT09',         'operator': 'Microsoft',       'city': 'East Wenatchee','lat': 47.413, 'lon': -120.310, 'source': 'reported'},
    {'name': 'Microsoft Malaga Campus',       'operator': 'Microsoft',       'city': 'Malaga',        'lat': 47.369, 'lon': -120.332, 'source': 'reported'},
    {'name': 'Sabey SDC Columbia',            'operator': 'Sabey',           'city': 'East Wenatchee','lat': 47.411, 'lon': -120.307, 'source': 'reported'},

    # ── Seattle / King County ──────────────────────────────────────────────────
    {'name': 'Equinix SE2 Seattle',           'operator': 'Equinix',         'city': 'Seattle',       'lat': 47.617, 'lon': -122.336, 'source': 'reported'},
    {'name': 'Westin Building Exchange',      'operator': 'Various',         'city': 'Seattle',       'lat': 47.616, 'lon': -122.336, 'source': 'reported'},
    {'name': 'Verizon Seattle',               'operator': 'Verizon',         'city': 'Seattle',       'lat': 47.605, 'lon': -122.334, 'source': 'reported'},
    {'name': 'HorizonIQ Seattle (Tukwila)',   'operator': 'HorizonIQ',       'city': 'Tukwila',       'lat': 47.468, 'lon': -122.268, 'source': 'reported'},
    {'name': 'ColoCrossing SEA1 (Tukwila)',   'operator': 'ColoCrossing',    'city': 'Tukwila',       'lat': 47.465, 'lon': -122.249, 'source': 'reported'},

    # ── Spokane / Liberty Lake ─────────────────────────────────────────────────
    {'name': 'Verizon Liberty Lake',          'operator': 'Verizon',         'city': 'Liberty Lake',  'lat': 47.682, 'lon': -117.119, 'source': 'reported'},

    # ── Proposed ──────────────────────────────────────────────────────────────
    {'name': 'Digital Realty (proposed)',              'operator': 'Digital Realty',  'city': 'Unincorporated', 'lat': 47.609, 'lon': -122.338, 'source': 'proposed'},
    {'name': 'Amazon Wallula Gap (proposed)',          'operator': 'Amazon/AWS',      'city': 'Burbank',        'lat': 46.195, 'lon': -119.042, 'source': 'proposed'},
    {'name': 'Atlas Agro Richland DC1 (proposed)',    'operator': 'Atlas Agro',      'city': 'Richland',       'lat': 46.365, 'lon': -119.365, 'source': 'proposed'},
    {'name': 'Trammell Crow Lewis Clark (proposed)',  'operator': 'Trammell Crow',   'city': 'West Richland',  'lat': 46.280, 'lon': -119.470, 'source': 'proposed'},
]

df  = pd.DataFrame(facilities)
gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['lon'], df['lat']), crs='EPSG:4326')

RAW    = Path('data/raw')
STATIC = Path('static')

gdf.to_file(RAW    / 'datacenters.geojson', driver='GeoJSON')
gdf.to_file(STATIC / 'datacenters.geojson', driver='GeoJSON')

print(f'Saved {len(gdf)} facilities')
for _, r in gdf.iterrows():
    print(f"  {r['city']:16s}  {r['name']}")
