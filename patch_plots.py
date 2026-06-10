"""Patch the four plotting cells in NB2 and NB3 with corrected dark-theme styling."""
import json

NB2_CELL16 = """\
DARK_BG = '#1a1a2e'
LAYER_CMAP = 'RdYlGn'
WHITE = 'white'

plt.rcParams.update({
    'text.color': WHITE,
    'axes.labelcolor': WHITE,
    'xtick.color': WHITE,
    'ytick.color': WHITE,
    'font.size': 18,
})

layers = [
    ('tx_score',    'Transmission Proximity',     '(1 = adjacent to HV line)'),
    ('water_score', 'Water Availability',          '(1 = highest precip / lowest stress)'),
    ('ej_score',    'Community Burden (EJScreen)', '(1 = lowest demographic burden)'),
]

fig, axes = plt.subplots(1, 3, figsize=(24, 9), facecolor=DARK_BG)

for ax, (col, title, subtitle) in zip(axes, layers):
    ax.set_facecolor(DARK_BG)
    wa.boundary.plot(ax=ax, color='#4a4a6a', linewidth=1.0, zorder=1)
    n_before = len(fig.axes)
    grid.plot(column=col, ax=ax, cmap=LAYER_CMAP, vmin=0, vmax=1,
              legend=True, legend_kwds={'shrink': 0.65, 'label': '0 = poor  /  1 = good'},
              alpha=0.85, zorder=2)
    if len(fig.axes) > n_before:
        cb_ax = fig.axes[-1]
        cb_ax.tick_params(labelsize=16, colors=WHITE)
        cb_ax.yaxis.label.set_color(WHITE)
        cb_ax.yaxis.label.set_size(16)
    _rep = dc_gdf[dc_gdf['source'] == 'reported']
    _prop = dc_gdf[dc_gdf['source'] == 'proposed']
    ax.scatter(_rep.geometry.x, _rep.geometry.y,
               c=WHITE, s=120, marker='D', zorder=5,
               edgecolors='black', linewidths=0.8)
    ax.scatter(_prop.geometry.x, _prop.geometry.y,
               facecolors='none', s=120, marker='D', zorder=5,
               edgecolors='black', linewidths=1.5)
    ax.set_title(f'{title}\\n{subtitle}', color=WHITE, fontsize=22, pad=10, linespacing=1.4)
    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for spine in ax.spines.values():
        spine.set_edgecolor('#4a4a6a')

plt.suptitle('Washington State: Data Center Siting Stress Indicators\\n'
             'White filled = existing  /  white outline = proposed',
             color=WHITE, fontsize=24, y=0.90)
plt.tight_layout(rect=[0, 0, 1, 0.86])
plt.savefig(PROCESSED / 'indicators.png', dpi=150, bbox_inches='tight',
            facecolor=fig.get_facecolor())
plt.show()
print('Saved to data/processed/indicators.png')
"""

NB2_CELL18 = """\
fig, ax = plt.subplots(figsize=(16, 10), facecolor=DARK_BG)
ax.set_facecolor(DARK_BG)

plt.rcParams.update({
    'text.color': 'white',
    'axes.labelcolor': 'white',
    'xtick.color': 'white',
    'ytick.color': 'white',
    'font.size': 18,
})

wa.boundary.plot(ax=ax, color='#4a4a6a', linewidth=1.0, zorder=1)

n_before = len(fig.axes)
grid.plot(
    column='composite', ax=ax,
    cmap='RdYlGn', vmin=0, vmax=1, alpha=0.88,
    legend=True,
    legend_kwds={
        'label': 'Composite Suitability (0=poor / 1=ideal)',
        'orientation': 'horizontal',
        'shrink': 0.5, 'pad': 0.05
    },
    zorder=2
)
if len(fig.axes) > n_before:
    cb_ax = fig.axes[-1]
    cb_ax.tick_params(labelsize=16, colors='white')
    cb_ax.xaxis.label.set_color('white')
    cb_ax.xaxis.label.set_size(16)

source_styles = {
    'reported':  ('white',  180, 'D', 'Known data center'),
    'proposed':  ('#FFB347', 150, 'D', 'Proposed data center'),
    'OSM':       ('#FF4444', 100, 'o', 'OSM data center'),
}
for source, (color, size, marker, label) in source_styles.items():
    grp = dc_gdf[dc_gdf['source'] == source]
    if len(grp) == 0:
        continue
    ax.scatter(grp.geometry.x, grp.geometry.y,
               c=color, s=size, marker=marker, zorder=6,
               edgecolors='black', linewidths=0.6, label=label)
    for _, row in grp.iterrows():
        ax.annotate(row['name'], (row.geometry.x, row.geometry.y),
                    xytext=(5, 3), textcoords='offset points',
                    fontsize=11, color='#eeeeee', zorder=7)

leg = ax.legend(loc='lower left', framealpha=0.35,
                facecolor=DARK_BG, edgecolor='#4a4a6a', fontsize=16)
for t in leg.get_texts():
    t.set_color('white')

ax.set_title(
    'Composite Siting Suitability: Washington State\\n'
    'Weights: 40% grid access + 35% water availability + 25% community burden (EJScreen)',
    color='white', fontsize=20, pad=14
)
ax.set_xlabel('')
ax.set_ylabel('')
ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
for spine in ax.spines.values():
    spine.set_edgecolor('#4a4a6a')

plt.tight_layout()
plt.savefig(PROCESSED / 'composite_suitability.png', dpi=150,
            bbox_inches='tight', facecolor=fig.get_facecolor())
plt.show()
print('Saved to data/processed/composite_suitability.png')
"""

NB3_CELL12 = """\
DARK_BG = '#1a1a2e'
WHITE = 'white'

plt.rcParams.update({
    'text.color': WHITE,
    'axes.labelcolor': WHITE,
    'xtick.color': WHITE,
    'ytick.color': WHITE,
    'font.size': 18,
})

fig, axes = plt.subplots(1, 3, figsize=(24, 9), facecolor=DARK_BG)

risk_layers = [
    ('seismic_score', 'Seismic Safety',           '(1=low hazard / 0=high PGA)'),
    ('flood_score',   'Flood Safety',              '(1=outside SFHA / 0=in SFHA)'),
    ('risk_adjusted', 'Risk-Adjusted Composite',   '(60% NB2 + 20% seismic + 20% flood)'),
]

for ax, (col, title, subtitle) in zip(axes, risk_layers):
    ax.set_facecolor(DARK_BG)
    wa.boundary.plot(ax=ax, color='#4a4a6a', linewidth=1.0, zorder=1)
    n_before = len(fig.axes)
    grid.plot(column=col, ax=ax, cmap='RdYlGn', vmin=0, vmax=1,
              legend=True, legend_kwds={'shrink': 0.65, 'label': '0=poor / 1=ideal'},
              alpha=0.85, zorder=2)
    if len(fig.axes) > n_before:
        cb_ax = fig.axes[-1]
        cb_ax.tick_params(labelsize=16, colors=WHITE)
        cb_ax.yaxis.label.set_color(WHITE)
        cb_ax.yaxis.label.set_size(16)
    _rep = dc_gdf[dc_gdf['source'] == 'reported']
    _prop = dc_gdf[dc_gdf['source'] == 'proposed']
    ax.scatter(_rep.geometry.x, _rep.geometry.y,
               c=WHITE, s=120, marker='D', zorder=5,
               edgecolors='black', linewidths=0.8)
    ax.scatter(_prop.geometry.x, _prop.geometry.y,
               facecolors='none', s=120, marker='D', zorder=5,
               edgecolors='black', linewidths=1.5)
    ax.set_title(f'{title}\\n{subtitle}', color=WHITE, fontsize=22, pad=10, linespacing=1.4)
    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for spine in ax.spines.values():
        spine.set_edgecolor('#4a4a6a')

plt.suptitle('Washington State: Risk Modifiers and Risk-Adjusted Siting Suitability\\n'
             'White filled = existing  /  outline = proposed',
             color=WHITE, fontsize=24, y=0.90)
plt.tight_layout(rect=[0, 0, 1, 0.86])
plt.savefig(PROCESSED / 'risk_layers.png', dpi=150, bbox_inches='tight',
            facecolor=fig.get_facecolor())
plt.show()
print('Saved to data/processed/risk_layers.png')
"""

NB3_CELL15 = """\
fig, ax = plt.subplots(figsize=(16, 10), facecolor=DARK_BG)
ax.set_facecolor(DARK_BG)

plt.rcParams.update({
    'text.color': 'white',
    'axes.labelcolor': 'white',
    'xtick.color': 'white',
    'ytick.color': 'white',
    'font.size': 18,
})

wa.boundary.plot(ax=ax, color='#4a4a6a', linewidth=1.0, zorder=1)

n_before = len(fig.axes)
grid.plot(column='risk_adjusted', ax=ax, cmap='RdYlGn', vmin=0, vmax=1, alpha=0.80,
          legend=True,
          legend_kwds={'label': 'Risk-Adjusted Suitability (0=poor / 1=ideal)',
                       'orientation': 'horizontal', 'shrink': 0.5, 'pad': 0.05},
          zorder=2)
if len(fig.axes) > n_before:
    cb_ax = fig.axes[-1]
    cb_ax.tick_params(labelsize=16, colors='white')
    cb_ax.xaxis.label.set_color('white')
    cb_ax.xaxis.label.set_size(16)

ax.scatter(dc_gdf.geometry.x, dc_gdf.geometry.y,
           c='white', s=150, marker='D', zorder=6,
           edgecolors='black', linewidths=0.6, label='Existing / proposed DC')

wa_union_geom = wa.geometry.unary_union
wa_canceled = joined_c[joined_c.geometry.within(wa_union_geom)]
ax.scatter(wa_canceled.geometry.x, wa_canceled.geometry.y,
           c='#FF4444', s=200, marker='X', zorder=7,
           edgecolors='white', linewidths=1.0, label='Canceled / blocked (WA)')

for _, row in wa_canceled.iterrows():
    short = row['name'].split('(')[0].strip()
    ax.annotate(short, (row.geometry.x, row.geometry.y),
                xytext=(8, 4), textcoords='offset points',
                fontsize=13, color='#FF9999', zorder=8)

leg = ax.legend(loc='lower left', framealpha=0.35,
                facecolor=DARK_BG, edgecolor='#4a4a6a', fontsize=16)
for t in leg.get_texts():
    t.set_color('white')

ax.set_title(
    'Risk-Adjusted Siting Suitability with Canceled/Blocked Projects (WA)\\n'
    'Red X = canceled or blocked; white diamond = existing/proposed',
    color='white', fontsize=20, pad=14
)
ax.set_xlabel('')
ax.set_ylabel('')
ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
for spine in ax.spines.values():
    spine.set_edgecolor('#4a4a6a')

plt.tight_layout()
plt.savefig(PROCESSED / 'risk_adjusted_validation.png', dpi=150,
            bbox_inches='tight', facecolor=fig.get_facecolor())
plt.show()
print('Saved to data/processed/risk_adjusted_validation.png')
"""


def lines(src):
    result = []
    for line in src.split('\n'):
        result.append(line + '\n')
    if result and result[-1] == '\n':
        result[-1] = ''
    return result


def patch_nb(path, patches):
    with open(path) as f:
        nb = json.load(f)
    changed = 0
    for cell in nb['cells']:
        cid = cell.get('id', '')
        if cid in patches:
            cell['source'] = lines(patches[cid])
            cell['outputs'] = []
            cell['execution_count'] = None
            changed += 1
            print(f'  patched cell {cid}')
    if changed != len(patches):
        print(f'WARNING: expected {len(patches)} patches, applied {changed}')
    with open(path, 'w') as f:
        json.dump(nb, f, indent=1)
    print(f'Saved {path}')


print('Patching NB2...')
patch_nb('02_stress_indicators.ipynb', {
    'a0000017': NB2_CELL16,
    'a0000019': NB2_CELL18,
})

print('Patching NB3...')
patch_nb('03_risk_modifiers.ipynb', {
    '9sf9nn4p': NB3_CELL12,
    '656a0m7d': NB3_CELL15,
})

print('Done.')
