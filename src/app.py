from flask import Flask, render_template, send_from_directory, redirect, abort
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))
try:
    from config import STATES
    _STATE_NAMES = {k: v['name'] for k, v in STATES.items()}
except Exception:
    _STATE_NAMES = {}

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


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5016))
    app.run(host='0.0.0.0', port=port, debug=False)
