"""
Worked example of the custom hitter chart contract (tier-3 schools).

A school's `custom_hitter_report.py` may define `get_charts(source, batter_id)` returning a list of
`CustomChart(title, figure)`, where `figure` is a Plotly `{'data': [...], 'layout': {...}}`. The page
draws it (and re-colors it for dark mode) and the browser renders the PNG the PDF uses, so a script
never writes an image file -- and never imports matplotlib, which is no longer installed.

Conventions that make a chart behave like the app's own:
  * Build the layout with `plotly_charts.base_layout(...)` (fonts, grid, margins, transparent background).
    Pass `equal_aspect=False` unless both axes are in the same unit.
  * Pass every list of numbers through `plotly_charts.floats(...)`: NaN becomes null. A bare NaN is not
    valid JSON, and `hitter_report.custom_charts` skips a chart that isn't strict JSON.
  * Name a layout shape 'ink' or 'muted' to have it follow the light/dark theme; a shape with no name keeps
    the color you gave it. Text and axes follow the theme automatically.
  * Return at most 6 charts. Anything that isn't a valid CustomChart is logged and skipped, so one bad
    chart never takes down the report.

Upload a script like this the way you upload any custom report (the master panel); school assets are not
kept in git.

This is the same chart Winthrop's script returns: exit velocity against launch angle for every ball in play,
with the barrel zone shaded.
"""
import pandas as pd

from app.services.hitter_report import HARD_HIT_MPH, batter_rows
from app.services.hitter_stats import CustomChart
from app.services.plotly_charts import base_layout, floats


def get_charts(source: pd.DataFrame, batter_id: str | int) -> list[CustomChart]:
    rows = batter_rows(source, batter_id)
    if 'PitchCall' not in rows.columns:
        return []
    batted = rows[rows['PitchCall'] == 'InPlay'].copy()
    batted['_Angle'] = pd.to_numeric(batted.get('Angle'), errors='coerce')
    batted['_ExitSpeed'] = pd.to_numeric(batted.get('ExitSpeed'), errors='coerce')
    batted = batted.dropna(subset=['_Angle', '_ExitSpeed'])
    if batted.empty:
        return []

    layout = base_layout('Launch Angle (deg)', 'Exit Velocity (mph)', (-40, 90), (40, 120), equal_aspect=False)
    layout['shapes'] = [{   # no name: the zone keeps its red in dark mode
        'type': 'rect', 'x0': 10, 'x1': 35, 'y0': HARD_HIT_MPH, 'y1': 120,
        'fillcolor': 'rgba(210,45,73,0.12)', 'line': {'color': '#d22d49', 'width': 1, 'dash': 'dash'},
        'layer': 'below',
    }]
    figure = {
        'data': [{
            'type': 'scatter', 'mode': 'markers', 'showlegend': False,
            'x': floats(batted['_Angle'], 1), 'y': floats(batted['_ExitSpeed'], 1),
            'hovertemplate': 'LA %{x:.0f}\u00b0<br>EV %{y:.1f} mph<extra></extra>',
            'marker': {'color': '#2a78d6', 'size': 9, 'opacity': 0.85},
        }],
        'layout': layout,
    }
    return [CustomChart('Exit Velocity vs Launch Angle', figure)]
