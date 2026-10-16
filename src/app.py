from flask import Flask, render_template, send_from_directory, redirect, abort, Response, request
import json
import os
import sys
import sqlite3
import hashlib
import statistics
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))
try:
    from config import STATES
    _STATE_NAMES = {k: v['name'] for k, v in STATES.items()}
except Exception:
    _STATE_NAMES = {}

REGIONS = {
    "WA": {
        "seattle": {
            "name": "Seattle",
            "zips": [
                "98101","98102","98103","98104","98105","98106","98107","98108","98109",
                "98112","98115","98116","98117","98118","98119","98121","98122","98125",
                "98126","98133","98134","98136","98144","98146","98155","98177","98178",
                "98195","98199",
            ],
            "center": [47.61, -122.33],
            "zoom": 11,
            "policy_note": (
                "The Seattle City Council passed a moratorium on new data center development "
                "exceeding 20 MW in April 2026, citing grid congestion and displacement "
                "pressure in industrial areas. Any siting recommendation within Seattle "
                "city limits is subject to this restriction pending council review or expiration."
            ),
            "seismic_note": (
                "Seattle sits above the Seattle Fault zone and within the Cascadia subduction "
                "zone influence area. PGAM values across all 29 Seattle ZCTAs range 0.32–0.35g "
                "— roughly 3–5× higher than preferred eastern WA sites (0.08–0.15g). "
                "Seismic risk is near-uniform across the city and does not differentiate ZCTAs "
                "meaningfully, but represents a fixed elevated risk premium for any siting decision here."
            ),
        }
    }
}

SURVEY_INDICATORS = [
    ('tx',       'Grid access',           'Proximity to high-voltage transmission lines'),
    ('water',    'Water availability',    'Annual precipitation and surface water'),
    ('ej',       'Community burden',      'Poverty and minority share (EJScreen)'),
    ('seismic',  'Seismic safety',        'Earthquake hazard (inverse USGS PGAM)'),
    ('flood',    'Flood safety',          'Outside FEMA flood zones'),
    ('contam',   'Contamination risk',    'Proximity to EPA toxic release facilities'),
    ('waterway', 'Waterway safety',       'Distance from major rivers'),
    ('geo',      'Geothermal opportunity','Heat flow for cooling or co-generation'),
    ('flat',     'Terrain flatness',      'Buildable slope'),
    ('pop',      'Population exposure',   'Residential density nearby (inverted)'),
    ('aquifer',  'Aquifer depth',         'Groundwater depth and sensitivity'),
    ('soil',     'Soil drainage',         'Soil permeability and spill containment risk'),
]

PARCEL_STUDIES = {
    "WA": {
        "grant": "grant_county_web.geojson",
        "tri":   "tri_cities_web.geojson",
    }
}

app = Flask(__name__,
            template_folder=str(PROJECT_ROOT / 'templates'),
            static_folder=str(PROJECT_ROOT / 'static'))

SURVEY_DB = PROJECT_ROOT / 'data' / 'survey.db'
_weights_cache = {}  # {(state, region): (timestamp, result_dict)}


def init_survey_db():
    db = sqlite3.connect(str(SURVEY_DB))
    db.execute("""
        CREATE TABLE IF NOT EXISTS survey_responses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            region       TEXT NOT NULL,
            state        TEXT NOT NULL,
            zip_code     TEXT NOT NULL,
            ip_hash      TEXT NOT NULL,
            rankings     TEXT NOT NULL,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_one_per_ip
            ON survey_responses (region, state, ip_hash)
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS survey_snapshots (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            region         TEXT NOT NULL,
            state          TEXT NOT NULL,
            label          TEXT NOT NULL,
            weights        TEXT NOT NULL,
            response_count INTEGER NOT NULL,
            snapshot_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    db.close()


def get_survey_zips(state_upper, region):
    region_cfg = REGIONS.get(state_upper, {}).get(region, {})
    if region_cfg:
        return set(region_cfg['zips'])
    filename = PARCEL_STUDIES.get(state_upper, {}).get(region)
    if filename:
        path = _data_dir(state_upper) / 'parcels' / filename
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            return {str(ft['properties']['zcta']) for ft in data['features']
                    if ft['properties'].get('zcta')}
    return set()


def compute_community_weights(state_upper, region):
    ind_keys = [k for k, _, _ in SURVEY_INDICATORS]
    N = len(ind_keys)
    db = sqlite3.connect(str(SURVEY_DB))
    rows = db.execute(
        "SELECT rankings FROM survey_responses WHERE state=? AND region=?",
        (state_upper, region)
    ).fetchall()
    db.close()
    if not rows:
        equal = 1.0 / N
        return {k: equal for k in ind_keys}
    point_lists = {k: [] for k in ind_keys}
    for (rankings_json,) in rows:
        r = json.loads(rankings_json)
        for k in ind_keys:
            rank = r.get(k)
            pts = (N + 1 - int(rank)) if rank is not None else 0
            point_lists[k].append(pts)
    means  = {k: statistics.mean(v) for k, v in point_lists.items()}
    stdevs = {k: statistics.stdev(v) if len(v) > 1 else 0.0 for k, v in point_lists.items()}
    raw    = {k: means[k] / (1.0 + stdevs[k]) for k in ind_keys}
    total  = sum(raw.values()) or 1.0
    return {k: raw[k] / total for k in ind_keys}


def _data_dir(state_upper):
    return PROJECT_ROOT / 'data' / state_upper


@app.route('/')
def root():
    return redirect('/wa/')


@app.route('/reports/pnw-water-stress', strict_slashes=False)
def report_pnw_water_stress():
    """Static findings snapshot sourced from Merascope's national water-stress
    layer. Data is a one-time generated JSON, not a live cross-service call --
    regenerate with merascope's scripts/analysis_pnw_water_stress.py if it
    goes stale. Rebuilt 2026-08-06: dropped the invented "Columbia Corridor"
    sub-region for full WA+OR vs. the 7 Colorado River Compact states, then
    dropped ZCTA data entirely in favor of reading Aqueduct's own watershed
    polygons directly (area-weighted, no ZCTA join/fill step) -- see
    contexts/datacenter_siting/CONTEXT.md for the full history. Data-center
    overlay dropped 2026-08-06 (fourth pass), then reinstated (fifth pass)
    once merascope's dc_tracker.py could back every marker with 2+
    independent sources instead of an uncited/stale citation list."""
    path = PROJECT_ROOT / 'data' / 'reports' / 'pnw_water_stress.json'
    if not path.exists():
        abort(404)
    with open(path) as f:
        data = json.load(f)
    return render_template('report_pnw_water_stress.html', **data)


def _send_report_asset(directory, filename):
    """These report data files (geojson/png/json under data/reports/) get
    regenerated in place, sometimes with different content or dimensions at
    the exact same URL, during active iteration -- a browser that cached an
    older version of one file while fetching a fresh version of a paired
    file (e.g. an old whp_wa.png with a new whp_wa_bounds.json) will silently
    render a stretched/misaligned combination that looks like a real
    georeferencing bug but isn't one. Force revalidation on every request
    rather than trust Flask's default send_file caching for these."""
    if not (directory / filename).exists():
        abort(404)
    resp = send_from_directory(str(directory), filename)
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@app.route('/reports/tracked_datacenters.geojson')
def tracked_datacenters():
    """Real data-center sites tracked in merascope's datacenters.db, each
    backed by logged sources -- generated via
    `python3 scripts/dc_tracker.py export-geojson`. `confirmed` (2+
    distinct-publisher sources) vs. not is a real property on each feature;
    the map styles them differently rather than presenting every claim with
    equal confidence."""
    return _send_report_asset(PROJECT_ROOT / 'data' / 'reports', 'tracked_datacenters.geojson')


@app.route('/reports/pnw_watersheds.geojson')
def pnw_watersheds():
    """The actual WRI Aqueduct watershed polygons under WA/OR (~293 shapes),
    clipped to the two states -- generated by merascope's
    scripts/export_pnw_watersheds.py. The map draws these instead of coloring
    1,033 ZCTA shapes with a watershed-resolution value, which would make the
    data look higher-resolution than it actually is."""
    return _send_report_asset(PROJECT_ROOT / 'data' / 'reports', 'pnw_watersheds.geojson')


@app.route('/reports/compact_watersheds.geojson')
def compact_watersheds():
    """The actual WRI Aqueduct watershed polygons under the 7 Colorado River
    Compact states (~807 shapes) -- same export script, same reasoning, for
    visual comparison against the WA/OR layer above."""
    return _send_report_asset(PROJECT_ROOT / 'data' / 'reports', 'compact_watersheds.geojson')


@app.route('/reports/wa-fire-risk', strict_slashes=False)
def report_wa_fire_risk():
    """Static findings snapshot sourced from Merascope's WA fire history +
    risk analysis -- same cross-service pattern as report_pnw_water_stress
    above (one-time generated JSON, not a live call). Two real layers, not
    an invented composite: MTBS burn perimeters (real fire history) and
    USFS Wildfire Hazard Potential (agency-scored risk index), matched
    against the same tracked data-center site list. Regenerate with
    merascope's scripts/analysis_wa_fire_risk.py if it goes stale."""
    path = PROJECT_ROOT / 'data' / 'reports' / 'wa_fire_risk.json'
    if not path.exists():
        abort(404)
    with open(path) as f:
        data = json.load(f)
    return render_template('report_wa_fire_risk.html', **data)


@app.route('/reports/wa_fire_perimeters.geojson')
def wa_fire_perimeters():
    """Real MTBS burn perimeter polygons clipped to WA (650 shapes, 1984-2024)
    -- generated by merascope's scripts/export_wa_fire_perimeters.py. Actual
    burn footprints, not an administrative or invented boundary -- same
    reasoning as drawing real watershed polygons instead of a ZCTA join."""
    return _send_report_asset(PROJECT_ROOT / 'data' / 'reports', 'wa_fire_perimeters.geojson')


@app.route('/reports/whp_wa.png')
def whp_wa_png():
    """Colorized USFS Wildfire Hazard Potential raster, cropped and masked
    to WA's real boundary -- shown as an image overlay (the raster's native
    form) rather than vectorized into artificial zones. Generated by
    merascope's scripts/render_whp_png.py. Paired with whp_wa_bounds.json --
    see _send_report_asset for why both must never be served from a stale
    browser cache independently of each other."""
    return _send_report_asset(PROJECT_ROOT / 'data' / 'reports', 'whp_wa.png')


@app.route('/reports/whp_wa_bounds.json')
def whp_wa_bounds():
    """Leaflet imageOverlay bounds ([[south,west],[north,east]]) for whp_wa.png."""
    return _send_report_asset(PROJECT_ROOT / 'data' / 'reports', 'whp_wa_bounds.json')


@app.route('/<state>/', strict_slashes=False)
def state_index(state):
    su = state.upper()
    if not (_data_dir(su) / 'grid_scores.geojson').exists():
        abort(404)
    state_name = _STATE_NAMES.get(su, su)
    return render_template('index.html', state=su, state_lower=su.lower(),
                           state_name=state_name)


@app.route('/<state>/grid_scores.geojson')
def state_grid(state):
    su = state.upper()
    d = _data_dir(su)
    if not (d / 'grid_scores.geojson').exists():
        abort(404)
    return send_from_directory(str(d), 'grid_scores.geojson')


@app.route('/<state>/transmission.geojson')
def state_transmission(state):
    su = state.upper()
    d = _data_dir(su) / 'raw'
    if not (d / 'transmission.geojson').exists():
        abort(404)
    return send_from_directory(str(d), 'transmission.geojson')


@app.route('/<state>/datacenters.geojson')
def state_datacenters(state):
    su = state.upper()
    d = _data_dir(su) / 'raw'
    if not (d / 'datacenters.geojson').exists():
        abort(404)
    return send_from_directory(str(d), 'datacenters.geojson')


@app.route('/<state>/study/', strict_slashes=False)
def state_study(state):
    su = state.upper()
    if not (_data_dir(su) / 'zcta' / 'grid_scores.geojson').exists():
        abort(404)
    state_name = _STATE_NAMES.get(su, su)
    return render_template('study.html', state=su, state_lower=su.lower(),
                           state_name=state_name)


@app.route('/<state>/zcta/grid_scores.geojson')
def state_zcta_grid(state):
    su = state.upper()
    d = _data_dir(su) / 'zcta'
    if not (d / 'grid_scores.geojson').exists():
        abort(404)
    return send_from_directory(str(d), 'grid_scores.geojson')


@app.route('/wa/study/grant/', strict_slashes=False)
def grant_study():
    web_path = _data_dir('WA') / 'parcels' / 'grant_county_web.geojson'
    if not web_path.exists():
        abort(404)
    with open(web_path) as f:
        data = json.load(f)
    features = data['features']
    web_count = len(features)

    score_cols = [
        ('water_score',   'Water availability (precipitation + surface water)'),
        ('ej_score',      'Community burden (EJ / poverty / minority share)'),
        ('seismic_score', 'Seismic safety (inverse PGAM)'),
        ('flood_score',   'Flood safety (inverse SFHA fraction)'),
        ('aquifer_score', 'Aquifer depth (USGS NWIS depth-to-water)'),
        ('soil_score',    'Soil drainage (SSURGO hydrologic group)'),
        ('slope_score',   'Terrain slope (SRTM flat fraction)'),
        ('tx_score',      'Grid access (transmission proximity)'),
        ('acreage_score', 'Parcel size (log-normalized)'),
        ('vacant_score',  'Development status (undeveloped fraction)'),
    ]
    score_ranges = []
    for col, label in score_cols:
        vals = [ft['properties'][col] for ft in features
                if ft['properties'].get(col) is not None]
        if vals:
            mn = min(vals); mx = max(vals)
            score_ranges.append({
                'col': col, 'label': label,
                'min': round(mn, 3),
                'mean': round(sum(vals) / len(vals), 3),
                'max': round(mx, 3),
                'spread': round(mx - mn, 3),
            })

    from collections import Counter
    dor_counter = Counter(
        str(ft['properties'].get('DepartmentOfRevenueCode', '') or '').strip().split(' ')[0]
        for ft in features
    )
    dor_labels = {'91': 'Undeveloped', '83': 'Ag Current Use', '81': 'Agriculture'}
    dor_breakdown = [
        {'code': code, 'label': dor_labels.get(code, 'Other'), 'count': cnt}
        for code, cnt in dor_counter.most_common(5)
        if code
    ]

    return render_template('parcel_study.html',
        state='WA', state_lower='wa', state_name='Washington',
        region='grant', region_name='Grant County',
        map_center=[47.2, -119.5], map_zoom=9,
        web_parcel_count=web_count,
        total_parcel_count=web_count,
        score_ranges=score_ranges,
        dor_breakdown=dor_breakdown,
        geojson_url='/wa/study/grant/parcels.geojson',
        context_note=(
            "The Quincy ZCTA (98848) — home to Microsoft, Vantage, and CyrusOne — receives "
            "a ZCTA-level composite of 0.567, lower than the Wilbur/Almira corridor "
            "(ZCTA 99135, composite 0.695). Quincy's EJ burden index has risen with "
            "concentrated industrial growth, and water availability scores reflect the "
            "Columbia Basin Project's largely subscribed allocation. Parcels in the Wilbur "
            "corridor offer comparable BPA transmission access at lower community burden, "
            "representing an underutilized alternative corridor."
        ),
        policy_note=(
            "Grant County PUD has publicly stated that Quincy's grid is at capacity. "
            "New transmission interconnection requires entering the BPA queue, with median "
            "wait times of 3–7 years for large loads. Sites outside the Quincy substation "
            "service area face significant grid integration timelines and should coordinate "
            "early with BPA and Grant PUD. The Bonneville hydro system is Washington's "
            "primary cost advantage for data center siting; the tradeoff is that Quincy-area "
            "water rights are largely subscribed under the Columbia Basin Project."
        ),
        seismic_note=(
            "Grant County PGAM values range 0.09–0.16g — among the lowest seismic hazard "
            "in Washington. This compares to 0.32–0.35g across Seattle ZCTAs and 0.20–0.28g "
            "in the Puget Sound industrial corridor. Seismic risk does not meaningfully "
            "differentiate parcels within Grant County and is not a significant constraint "
            "on siting here."
        ),
    )


@app.route('/wa/study/grant/parcels.geojson')
def grant_parcels_geojson():
    d = _data_dir('WA') / 'parcels'
    if not (d / 'grant_county_web.geojson').exists():
        abort(404)
    return send_from_directory(str(d), 'grant_county_web.geojson',
                               mimetype='application/json')


@app.route('/wa/study/tri/', strict_slashes=False)
def tri_study():
    web_path = _data_dir('WA') / 'parcels' / 'tri_cities_web.geojson'
    if not web_path.exists():
        abort(404)
    with open(web_path) as f:
        data = json.load(f)
    features = data['features']
    web_count = len(features)

    score_cols = [
        ('water_score',   'Water availability (precipitation + surface water)'),
        ('ej_score',      'Community burden (EJ / poverty / minority share)'),
        ('seismic_score', 'Seismic safety (inverse PGAM)'),
        ('flood_score',   'Flood safety (inverse SFHA fraction)'),
        ('aquifer_score', 'Aquifer depth (USGS NWIS depth-to-water)'),
        ('soil_score',    'Soil drainage (SSURGO hydrologic group)'),
        ('slope_score',   'Terrain slope (SRTM flat fraction)'),
        ('tx_score',      'Grid access (transmission proximity)'),
        ('acreage_score', 'Parcel size (log-normalized)'),
        ('vacant_score',  'Development status (undeveloped fraction)'),
    ]
    score_ranges = []
    for col, label in score_cols:
        vals = [ft['properties'][col] for ft in features
                if ft['properties'].get(col) is not None]
        if vals:
            mn = min(vals); mx = max(vals)
            score_ranges.append({
                'col': col, 'label': label,
                'min': round(mn, 3),
                'mean': round(sum(vals) / len(vals), 3),
                'max': round(mx, 3),
                'spread': round(mx - mn, 3),
            })

    from collections import Counter
    dor_counter = Counter(
        str(ft['properties'].get('DepartmentOfRevenueCode', '') or '').strip().split(' ')[0]
        for ft in features
    )
    dor_labels = {
        '83': 'Ag Current Use', '81': 'Agriculture',
        '91': 'Undeveloped', '39': 'Industrial', '68': 'Open Space/Rec',
    }
    dor_breakdown = [
        {'code': code, 'label': dor_labels.get(code, 'Other'), 'count': cnt}
        for code, cnt in dor_counter.most_common(5)
        if code and code != '0'
    ]

    return render_template('parcel_study.html',
        state='WA', state_lower='wa', state_name='Washington',
        region='tri', region_name='Tri-Cities (Benton + Franklin Counties)',
        map_center=[46.23, -119.2], map_zoom=10,
        web_parcel_count=web_count,
        total_parcel_count=web_count,
        score_ranges=score_ranges,
        dor_breakdown=dor_breakdown,
        geojson_url='/wa/study/tri/parcels.geojson',
        context_note=(
            "All Tri-Cities ZCTAs score water_score = 0.000 — the Columbia River's junior "
            "water rights are deeply subscribed in this basin, and Washington Ecology has "
            "placed restrictions on new industrial withdrawals east of McNary Dam. "
            "Transmission access is among the best in Washington: BPA's McNary-Ashe 500kV "
            "corridor runs directly through the region, and all area ZCTAs score above 0.86 "
            "on tx_score. The Hanford Nuclear Reservation — a 580-square-mile DOE site north "
            "of Richland — does not appear in county assessor records and is absent from this "
            "dataset; its surrounding private agricultural land scores well on transmission "
            "proximity but faces water constraints equally. Top parcels are large agricultural "
            "blocks (DOR 83: Agriculture Current Use) ranging 480–680 acres in the Kennewick "
            "and Pasco agricultural plain."
        ),
        policy_note=(
            "The Tri-Cities region is served by Benton REA, Franklin PUD, and Benton County "
            "PUD — three separate utilities with differing interconnection queues. BPA's "
            "McNary-Ashe 500kV corridor passes through the region, but load interconnection "
            "for large industrial customers (>50 MW) requires BPA transmission study and "
            "capacity reservation, with median timelines of 4–6 years for large loads. "
            "Water rights for industrial cooling are a hard constraint: any siting proposal "
            "requiring significant cooling water should plan for closed-loop or air-cooled "
            "systems and engage Washington Ecology on consumptive use permitting early. "
            "Benton County has been identified as a location of interest for large-scale "
            "data center development (Trammell Crow Sustainability Campus proposal, Atlas "
            "Agro industrial site)."
        ),
        seismic_note=(
            "Tri-Cities PGAM values range 0.08–0.12g across all area ZCTAs — among the "
            "lowest seismic hazard in Washington. The region sits on a stable Miocene "
            "basalt plateau well east of the Cascadia subduction zone influence area. "
            "This compares to 0.32–0.35g across Seattle ZCTAs and 0.20–0.28g in the "
            "Puget Sound industrial corridor. Seismic risk does not meaningfully "
            "differentiate parcels within the Tri-Cities region."
        ),
    )


@app.route('/wa/study/tri/parcels.geojson')
def tri_parcels_geojson():
    d = _data_dir('WA') / 'parcels'
    if not (d / 'tri_cities_web.geojson').exists():
        abort(404)
    return send_from_directory(str(d), 'tri_cities_web.geojson',
                               mimetype='application/json')


@app.route('/<state>/study/<region>/', strict_slashes=False)
def region_study(state, region):
    su = state.upper()
    rl = region.lower()
    region_cfg = REGIONS.get(su, {}).get(rl)
    if not region_cfg:
        abort(404)
    zcta_path = _data_dir(su) / 'zcta' / 'grid_scores.geojson'
    if not zcta_path.exists():
        abort(404)

    zips_set = set(region_cfg['zips'])
    with open(zcta_path) as f:
        data = json.load(f)
    features = [ft for ft in data['features'] if ft['properties'].get('zcta') in zips_set]

    gate_terrain   = sum(1 for ft in features if ft['properties'].get('flatness_score', 1) == 0)
    gate_protected = sum(1 for ft in features if ft['properties'].get('protected_score', 1) == 0)
    gate_clear     = len(features) - gate_terrain - gate_protected

    score_cols = [
        ('tx_score',            'Grid access'),
        ('water_score',         'Water availability'),
        ('ej_score',            'Community burden'),
        ('seismic_score',       'Seismic safety'),
        ('flood_score',         'Flood safety'),
        ('contamination_score', 'Contamination proximity'),
        ('waterway_score',      'Waterway safety'),
        ('geothermal_score',    'Geothermal opportunity'),
        ('flatness_score',      'Terrain flatness'),
        ('pop_exposure_score',  'Population exposure'),
    ]
    indicator_ranges = []
    for col, label in score_cols:
        vals = [ft['properties'][col] for ft in features
                if col in ft['properties'] and ft['properties'][col] is not None]
        if vals:
            mn = min(vals); mx = max(vals)
            indicator_ranges.append({
                'col': col, 'label': label,
                'min': round(mn, 3),
                'mean': round(sum(vals) / len(vals), 3),
                'max': round(mx, 3),
                'spread': round(mx - mn, 3),
            })

    state_name = _STATE_NAMES.get(su, su)
    return render_template('case_study.html',
        state=su, state_lower=su.lower(), state_name=state_name,
        region=rl, region_name=region_cfg['name'],
        map_center=region_cfg['center'], map_zoom=region_cfg['zoom'],
        zcta_count=len(features),
        gate_terrain=gate_terrain, gate_protected=gate_protected, gate_clear=gate_clear,
        indicator_ranges=indicator_ranges,
        policy_note=region_cfg.get('policy_note', ''),
        seismic_note=region_cfg.get('seismic_note', ''),
        geojson_url='/{}/study/{}/grid_scores.geojson'.format(su.lower(), rl),
    )


@app.route('/<state>/study/<region>/grid_scores.geojson')
def region_grid_geojson(state, region):
    su = state.upper()
    rl = region.lower()
    region_cfg = REGIONS.get(su, {}).get(rl)
    if not region_cfg:
        abort(404)
    zcta_path = _data_dir(su) / 'zcta' / 'grid_scores.geojson'
    if not zcta_path.exists():
        abort(404)
    zips_set = set(region_cfg['zips'])
    with open(zcta_path) as f:
        data = json.load(f)
    data['features'] = [ft for ft in data['features'] if ft['properties'].get('zcta') in zips_set]
    return Response(json.dumps(data), mimetype='application/json')


@app.route('/<state>/study/<region>/survey/', strict_slashes=False)
def survey_page(state, region):
    su = state.upper(); rl = region.lower()
    zips = get_survey_zips(su, rl)
    if not zips:
        abort(404)
    region_cfg = REGIONS.get(su, {}).get(rl, {})
    region_name = region_cfg.get('name', rl.replace('_', ' ').title())
    return render_template('survey.html',
        state=su, state_lower=su.lower(), state_name=_STATE_NAMES.get(su, su),
        region=rl, region_name=region_name,
        indicators=SURVEY_INDICATORS,
    )


@app.route('/<state>/study/<region>/survey/submit', methods=['POST'])
def survey_submit(state, region):
    su = state.upper(); rl = region.lower()
    zips = get_survey_zips(su, rl)
    if not zips:
        abort(404)
    data = request.get_json(silent=True) or {}
    zip_code = str(data.get('zip_code', '')).strip()
    rankings = data.get('rankings', {})
    if not zip_code or zip_code not in zips:
        return Response(json.dumps({'error': 'Please enter a ZIP code in the ' + region_name_for(su, rl) + ' area.'}),
                        status=400, mimetype='application/json')
    if not rankings:
        return Response(json.dumps({'error': 'Please rank at least one indicator.'}),
                        status=400, mimetype='application/json')
    ip_raw  = (request.headers.get('X-Forwarded-For', '') or request.remote_addr or '').split(',')[0].strip()
    ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()
    try:
        db = sqlite3.connect(str(SURVEY_DB))
        db.execute(
            "INSERT INTO survey_responses (region, state, zip_code, ip_hash, rankings) VALUES (?,?,?,?,?)",
            (rl, su, zip_code, ip_hash, json.dumps({k: int(v) for k, v in rankings.items()}))
        )
        db.commit()
        db.close()
    except sqlite3.IntegrityError:
        return Response(json.dumps({'error': 'One response per location is allowed.'}),
                        status=409, mimetype='application/json')
    _weights_cache.pop((su, rl), None)
    return Response(json.dumps({'ok': True}), mimetype='application/json')


def region_name_for(state_upper, region):
    cfg = REGIONS.get(state_upper, {}).get(region, {})
    return cfg.get('name', region.replace('_', ' ').title())


@app.route('/<state>/study/<region>/community_weights')
def community_weights_endpoint(state, region):
    su = state.upper(); rl = region.lower()
    if not get_survey_zips(su, rl):
        abort(404)
    now = time.time()
    cache_key = (su, rl)
    if cache_key in _weights_cache:
        ts, cached = _weights_cache[cache_key]
        if now - ts < 300:
            return Response(json.dumps(cached), mimetype='application/json')
    weights = compute_community_weights(su, rl)
    db = sqlite3.connect(str(SURVEY_DB))
    count = db.execute(
        "SELECT COUNT(*) FROM survey_responses WHERE state=? AND region=?",
        (su, rl)
    ).fetchone()[0]
    snap = db.execute(
        "SELECT label, weights, response_count, snapshot_at FROM survey_snapshots "
        "WHERE state=? AND region=? ORDER BY id DESC LIMIT 1",
        (su, rl)
    ).fetchone()
    db.close()
    snapshot = None
    if snap:
        snapshot = {'label': snap[0], 'weights': json.loads(snap[1]),
                    'response_count': snap[2], 'snapshot_at': snap[3]}
    result = {'weights': weights, 'response_count': count, 'snapshot': snapshot}
    _weights_cache[cache_key] = (now, result)
    return Response(json.dumps(result), mimetype='application/json')


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


init_survey_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5016))
    app.run(host='0.0.0.0', port=port, debug=False)
