"""State configuration table for the data center siting pipeline."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# (west, south, east, north) in WGS84
STATES = {
    "AL": {"name": "Alabama",             "fips": "01", "bbox": (-88.474, 30.144, -84.889, 35.008)},
    "AK": {"name": "Alaska",              "fips": "02", "bbox": (-179.231, 51.214, -129.979, 71.365)},
    "AZ": {"name": "Arizona",             "fips": "04", "bbox": (-114.815, 31.332, -109.045, 37.004)},
    "AR": {"name": "Arkansas",            "fips": "05", "bbox": (-94.617, 33.004, -89.644, 36.500)},
    "CA": {"name": "California",          "fips": "06", "bbox": (-124.409, 32.535, -114.131, 42.009)},
    "CO": {"name": "Colorado",            "fips": "08", "bbox": (-109.060, 36.992, -102.042, 41.003)},
    "CT": {"name": "Connecticut",         "fips": "09", "bbox": (-73.727, 40.951, -71.788, 42.050)},
    "DE": {"name": "Delaware",            "fips": "10", "bbox": (-75.789, 38.451, -74.984, 39.839)},
    "FL": {"name": "Florida",             "fips": "12", "bbox": (-87.635, 24.396, -80.031, 31.001)},
    "GA": {"name": "Georgia",             "fips": "13", "bbox": (-85.605, 30.358, -80.751, 35.001)},
    "HI": {"name": "Hawaii",              "fips": "15", "bbox": (-160.249, 18.776, -154.755, 22.235)},
    "ID": {"name": "Idaho",               "fips": "16", "bbox": (-117.243, 41.988, -111.043, 49.001)},
    "IL": {"name": "Illinois",            "fips": "17", "bbox": (-91.513, 36.970, -87.020, 42.508)},
    "IN": {"name": "Indiana",             "fips": "18", "bbox": (-88.099, 37.772, -84.785, 41.761)},
    "IA": {"name": "Iowa",                "fips": "19", "bbox": (-96.639, 40.376, -90.140, 43.501)},
    "KS": {"name": "Kansas",              "fips": "20", "bbox": (-102.051, 36.993, -94.588, 40.003)},
    "KY": {"name": "Kentucky",            "fips": "21", "bbox": (-89.572, 36.497, -81.965, 39.147)},
    "LA": {"name": "Louisiana",           "fips": "22", "bbox": (-94.042, 28.855, -88.758, 33.019)},
    "ME": {"name": "Maine",               "fips": "23", "bbox": (-71.085, 42.977, -66.950, 47.460)},
    "MD": {"name": "Maryland",            "fips": "24", "bbox": (-79.488, 37.886, -74.986, 39.723)},
    "MA": {"name": "Massachusetts",       "fips": "25", "bbox": (-73.508, 41.188, -69.928, 42.887)},
    "MI": {"name": "Michigan",            "fips": "26", "bbox": (-90.418, 41.696, -82.122, 48.306)},
    "MN": {"name": "Minnesota",           "fips": "27", "bbox": (-97.239, 43.500, -89.491, 49.384)},
    "MS": {"name": "Mississippi",         "fips": "28", "bbox": (-91.655, 30.174, -88.098, 34.996)},
    "MO": {"name": "Missouri",            "fips": "29", "bbox": (-95.774, 35.996, -89.099, 40.613)},
    "MT": {"name": "Montana",             "fips": "30", "bbox": (-116.049, 44.358, -104.040, 49.001)},
    "NE": {"name": "Nebraska",            "fips": "31", "bbox": (-104.053, 40.001, -95.308, 43.002)},
    "NV": {"name": "Nevada",              "fips": "32", "bbox": (-120.005, 35.002, -114.040, 42.002)},
    "NH": {"name": "New Hampshire",       "fips": "33", "bbox": (-72.557, 42.697, -70.703, 45.306)},
    "NJ": {"name": "New Jersey",          "fips": "34", "bbox": (-75.559, 38.789, -73.894, 41.357)},
    "NM": {"name": "New Mexico",          "fips": "35", "bbox": (-109.050, 31.332, -103.001, 37.000)},
    "NY": {"name": "New York",            "fips": "36", "bbox": (-79.763, 40.496, -71.857, 45.015)},
    "NC": {"name": "North Carolina",      "fips": "37", "bbox": (-84.322, 33.843, -75.460, 36.588)},
    "ND": {"name": "North Dakota",        "fips": "38", "bbox": (-104.049, 45.935, -96.554, 49.001)},
    "OH": {"name": "Ohio",                "fips": "39", "bbox": (-84.820, 38.403, -80.519, 42.327)},
    "OK": {"name": "Oklahoma",            "fips": "40", "bbox": (-103.002, 33.616, -94.431, 37.002)},
    "OR": {"name": "Oregon",              "fips": "41", "bbox": (-124.566, 41.992, -116.463, 46.236)},
    "PA": {"name": "Pennsylvania",        "fips": "42", "bbox": (-80.520, 39.720, -74.689, 42.269)},
    "RI": {"name": "Rhode Island",        "fips": "44", "bbox": (-71.863, 41.146, -71.120, 42.018)},
    "SC": {"name": "South Carolina",      "fips": "45", "bbox": (-83.354, 32.035, -78.541, 35.215)},
    "SD": {"name": "South Dakota",        "fips": "46", "bbox": (-104.058, 42.480, -96.436, 45.945)},
    "TN": {"name": "Tennessee",           "fips": "47", "bbox": (-90.310, 34.983, -81.647, 36.678)},
    "TX": {"name": "Texas",               "fips": "48", "bbox": (-106.645, 25.837, -93.508, 36.500)},
    "UT": {"name": "Utah",                "fips": "49", "bbox": (-114.053, 36.998, -109.041, 42.001)},
    "VT": {"name": "Vermont",             "fips": "50", "bbox": (-73.437, 42.727, -71.465, 45.017)},
    "VA": {"name": "Virginia",            "fips": "51", "bbox": (-83.675, 36.541, -75.242, 39.466)},
    "WA": {"name": "Washington",          "fips": "53", "bbox": (-124.733, 45.543, -116.916, 49.002)},
    "WV": {"name": "West Virginia",       "fips": "54", "bbox": (-82.644, 37.202, -77.719, 40.638)},
    "WI": {"name": "Wisconsin",           "fips": "55", "bbox": (-92.889, 42.492, -86.250, 47.309)},
    "WY": {"name": "Wyoming",             "fips": "56", "bbox": (-111.056, 40.995, -104.052, 45.006)},
    "DC": {"name": "District of Columbia","fips": "11", "bbox": (-77.120, 38.791, -76.909, 38.996)},
}


def utm_epsg(bbox):
    """Return UTM zone EPSG for the center of the given bbox (northern hemisphere)."""
    center_lon = (bbox[0] + bbox[2]) / 2
    zone = int((center_lon + 180) / 6) + 1
    return f"EPSG:{32600 + zone}"


def get_state(abbr: str) -> dict:
    abbr = abbr.upper()
    if abbr not in STATES:
        raise ValueError(f"Unknown state: {abbr}. Valid keys: {sorted(STATES)}")
    cfg = STATES[abbr].copy()
    cfg["abbr"] = abbr
    cfg["utm_epsg"] = utm_epsg(cfg["bbox"])
    cfg["bbox_str"] = "{},{},{},{}".format(*cfg["bbox"])  # west,south,east,north
    return cfg


def get_paths(abbr: str) -> tuple:
    """Return (project_root, raw_dir, processed_dir, grid_path).

    If the env var DC_SUBDIR is set (e.g. 'zcta'), grid_scores.geojson is written
    to data/{STATE}/{DC_SUBDIR}/ instead of data/{STATE}/. Scripts 03-07 are
    geometry-agnostic, so the same scripts serve both fishnet and ZCTA runs.
    """
    cfg = get_state(abbr)
    raw = PROJECT_ROOT / "data" / abbr / "raw"
    processed = PROJECT_ROOT / "data" / abbr / "processed"
    subdir = os.environ.get("DC_SUBDIR", "")
    study_root = PROJECT_ROOT / "data" / abbr / subdir if subdir else PROJECT_ROOT / "data" / abbr
    study_root.mkdir(parents=True, exist_ok=True)
    grid = study_root / "grid_scores.geojson"
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    return PROJECT_ROOT, raw, processed, grid
