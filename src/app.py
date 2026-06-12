from flask import Flask, render_template, send_from_directory, redirect, abort, Response
import json
import os
import sys
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

app = Flask(__name__,
            template_folder=str(PROJECT_ROOT / 'templates'),
            static_folder=str(PROJECT_ROOT / 'static'))


def _data_dir(state_upper):
    return PROJECT_ROOT / 'data' / state_upper


@app.route('/')
def root():
    return redirect('/wa/')


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


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5016))
    app.run(host='0.0.0.0', port=port, debug=False)
