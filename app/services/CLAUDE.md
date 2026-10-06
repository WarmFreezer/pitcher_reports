# app/services

Report-building and business logic. Pure Python/pandas — no Flask, no `current_user`,
no `db.session` in this folder (verified across `report.py`, `hitter_report.py`,
`pitch_stats.py`, `hitter_stats.py`, `report_lab_generator.py`, `custom_report_loader.py`).
Keep it that way: it is what lets the same functions serve the web preview, the on-demand
PDF export and the tests, and it keeps open the option of moving report building off the request
thread again.

## Filters, Plotly figures, chart images (pitching, batting, catching)

- `pitch_filters.PitchFilters` -- parsed + validated from the request, applied once to `source`
  (`apply`) before anything else is computed. `pitch_type_options`/`velo_bounds` feed the
  filter bar. A pitch with no tracked velocity is dropped only when a velo range is set.
- `plotly_charts` -- builds `{'data', 'layout'}` dicts directly (no `plotly` dependency; the
  browser's Plotly.js draws them). Everything goes through `_floats` so NaN becomes null --
  a bare `NaN` isn't valid JSON. Figures are light-themed; the page recolors them for dark
  mode using each shape's `name` ('ink'/'muted'). The heatmap is a numpy Gaussian KDE (Scott's
  rule x bw_adjust, like seaborn did), with a per-type fallback to points under
  `HEATMAP_MIN_PITCHES`. The velocity scale is pinned to the pitcher's own *unfiltered*
  Q1-Q3 (`velo_limits`) so colors don't shift as the sliders move.
- `pitcher_card` / `hitter_card` / `catcher_card` -- one person's tables/charts for given filters,
  shared by the web card and the PDF export so both are built from the same pitches. `chart_prefs`
  holds the validated view/color options. Charts are built by `plotly_charts` around one
  `_cloud_traces` core: a `ValueScale` says which column the color means (pitch velocity, exit
  velocity, framing value), and the figure functions (`location_figure`, `break_figure`,
  `spray_figure`, `catcher_figure`) only choose axes, field drawing and scale.
- `ab_chart` -- the per-at-bat panel in the pitch-by-pitch PDFs, drawn as ReportLab vector shapes (`Drawing`), built by `report_lab_generator` at render time from `ab.pitches`; nothing is stored on the at-bat dataclasses. `velo_scale` holds the cool-to-hot palette and the Q1-Q3 scale rule shared with `plotly_charts`.
- `chart_images` -- the only client-supplied input to a PDF is the chart PNGs; this validates
  and re-encodes them. Don't accept images any other way.

## StatTable pattern

Stat tables (`PitcherStatsTable`, `HitterDisciplineTable`, `CustomStatsTable`, etc., in
`pitch_stats.py`/`hitter_stats.py`) are `StatTable[RowT]` subclasses: a list of frozen
dataclass rows plus a `columns: ClassVar[list[Column]]` spec declaring header text and
`ColumnFormat` (percent/decimal/int/text) once. Consumers never format a value or
isinstance-check a column themselves — call `.to_reportlab_rows()` for a PDF table,
`.to_html(css_class)` for the web preview, `.to_dict()` for JSON. Adding a new stat table
means adding a dataclass + a `StatTable` subclass with its `columns` list, not writing a
new rendering path.

## Custom report loader contract (tier-3 schools)

`custom_report_loader.load_custom_module(school_id, filename)` exec's a school-uploaded
`custom_pitcher_report.py`/`custom_hitter_report.py` from
`storage/schools/<id>/assets/`. A module must expose whichever of these the report
needs; a missing attribute means "this school didn't implement that section" and is
handled as `None`, not an error:
- `get_stats(source, id) -> list[CustomStat]`
- `get_pitch_type_stats(source, id) -> list[CustomPitchTypeStatsTable]`
- `get_elements(gen, data) -> list` (raw ReportLab flowables, for `PDF_Generator`'s
  `generate_pitcher_report`/`generate_hitter_report` custom-report section)

Hitter side additionally supports `get_hit_type_stats` and `get_charts(source, id) ->
list[CustomChart]` -- a `CustomChart(title, figure)` whose figure is a Plotly
`{'data', 'layout'}` (build it with `plotly_charts.base_layout`/`floats`); the browser draws it
and renders the PDF's PNG, so a script never writes an image. `hitter_report.custom_charts`
validates what comes back and skips anything invalid. Every call site
wraps the module call in try/except and logs+returns `None` on failure — a broken
custom script degrades that one section, never the rest of the report. See the root
CLAUDE.md's TODO-adjacent note: this exec is unsandboxed by design (master-only,
CLI-provisioned upload gate) — don't loosen who can upload one without adding real
sandboxing first.

Custom stats reach the web preview (not just the PDF) via `custom_stats_table.to_html()`
in the JSON payload built by `pitching.py`/`batting.py` — if you add a new custom-*
function, thread it through both the PDF (`report_lab_generator.py`) and the JSON dict,
or it'll silently only show up in the download.

## report_lab_generator.py: branding + ink_mode

`PDF_Generator(school_id, branding, ink_mode='full_color')` resolves all report colors
from the `branding` dict (school's `primary`/`secondary`/`tertiary`/`accent`/`dark`/
`light`) — never hardcode a color here. `ink_mode='light_ink'` drops the colored header/
section-bar fills in favor of a plain thin rule (`_header_fill_commands()`); use that
helper for any new header-row TableStyle instead of writing `BACKGROUND`/`TEXTCOLOR`
directly, so new sections automatically respect the user's ink preference.
