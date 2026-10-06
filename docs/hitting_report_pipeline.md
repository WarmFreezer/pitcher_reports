# Hitting Report Pipeline

## Overview

Mirrors `docs/pitching_report_pipeline.md` structurally, with two differences:
a hitter report spans a date range across every archived game rather than a
single selection, and it now has the same tier-3 custom-stats extension
point the pitcher report does. Read the pitching doc first for shared
concepts (`StatTable`, the `report_theme` zone constants) -- they aren't
repeated here.

1. **Selection & orchestration** -- `app/routes/batting.py`. Resolves the
   requested date range against the archive, loops over each selected
   hitter, and calls the next three stages.
2. **Aggregation** -- `app/services/hitter_report.py`. Turns raw per-pitch
   TrackMan rows into per-hitter numbers (pandas aggregation, never
   row-by-row Python, per `CLAUDE.md`).
3. **Typed value objects** -- `app/services/hitter_stats.py`. Aggregation
   results are packaged into dataclasses/`StatTable`s, same as the pitcher
   side.
4. **PDF assembly** -- `app/services/report_lab_generator.py`.
   `PDF_Generator.generate_hitter_report()` takes one `HitterReportRequest`
   and lays out a ReportLab PDF from it.

A fifth, optional stage -- **tier-3 custom stats** -- lets a school inject
its own stats/charts/flowables into stages 2-4 via a Python file it owns.
See the dedicated section below.

## Entry point: `app/routes/batting.py`

Three routes share one `source` DataFrame (the archived games inside the date range, already
scoped to `current_user.school_id`), narrowed once by `PitchFilters.apply(source)` -- the pitch
type checkboxes and pitch-velocity range on the page -- before any stat or chart is computed:

- **`POST /api/batting/report`** streams NDJSON: a `meta` line (pitch types and velocity range for
  the filter bar, plus the account's chart defaults), one `report` card per hitter, then `done`.
- **`POST /api/batting/hitter`** rebuilds one card for new filters or chart options
  (`charts_only` skips the tables).
- **`POST /api/batting/export`** builds the PDF on demand from the browser-rendered spray-chart
  PNGs plus the current filters; the server recomputes every number itself.

For each hitter (`hitter_card.py`): `build_hitter_summary()`, `build_hitter_discipline_table()`,
`build_batted_ball_table()`, tier-3 custom stats if the school has any, and -- when the school is
active and tier >= 2 -- the two spray figures from `plotly_charts.spray_figure()`. A hitter with
no pitches passing the filters comes back as an `empty` card, not an error. Each hitter is wrapped
in its own `try/except` -- one failing doesn't stop the rest. The pitch-by-pitch PDF is a GET link
built on request (`/api/batting/pitch-by-pitch`), carrying the filters.

## Aggregation -- `app/services/hitter_report.py`

Raw rows are expected to carry the TrackMan columns listed in
`required_columns` (`hitter_report.py:63-83`) -- `BatterId`,
`TaggedPitchType`, `PlateLocSide`/`PlateLocHeight`, `PitchCall`,
`PlayResult`, `ExitSpeed`, `Angle`, `Bearing`, `Distance`, and friends. Key
functions:

- **`build_hitter_summary(source, batter_id)`** -- slash line (AVG/OBP/SLG),
  BB%/K%, and exit-velocity/launch-angle summary as a label -> display-string
  dict, rendered as the "Key Statistics" tile grid.
- **`build_hitter_discipline_table(source, batter_id)`** -- plate discipline
  per pitch type (Zone/Swing/Whiff/Chase/Contact). Zone and Chase are rated
  over *located* pitches only -- a `PlateLocSide`/`Height` of NaN is not
  evidence of a pitch off the plate, so it's excluded from those two
  denominators specifically, unlike Seen/Usage/Swing/Whiff/Contact which
  cover every pitch.
- **`build_batted_ball_table(source, batter_id)`** -- batted-ball mix by
  launch-angle bucket (`classify_hit_type`: Ground/Line/Fly/Pop), with exit
  velocity and distance per bucket.
- **Spray charts** (`plotly_charts.spray_figure`) -- landing spots from
  `Bearing`/`Distance` (TrackMan leaves `PitchLastMeasuredX/Z` empty, so those aren't usable
  here), one chart per pitcher side (`Left`/`Right`). Marker shape is the batted-ball type; color
  is the pitch type or, in velocity mode, *exit* velocity on a scale pinned to the hitter's own
  unfiltered first-to-third quartile. Drawn by the browser (Plotly.js); the PDF uses PNGs the
  browser renders from the same figures.

## Typed value objects -- `hitter_stats.py`

`hitter_stats.py` defines the concrete tables, following the same
`StatTable`/`Column`/`ColumnFormat` pattern as `pitch_stats.py`:

- `HitterDisciplineTable` (8 columns) / `BattedBallTable` (7 columns) --
  fixed schema, backing `build_hitter_discipline_table()`/
  `build_batted_ball_table()`.
- `CustomHitTypeStatsTable` -- the tier-3 hit-type table. Like
  `pitch_stats.CustomPitchTypeStatsTable`, its headers are derived at
  runtime from the union of each row's `stats` dict keys rather than a
  static `columns` list, since a school's script can add whatever stat
  names it wants per hit type.
- `HitterReportRequest` -- the single struct
  `PDF_Generator.generate_hitter_report()` takes, mirroring
  `pitch_stats.PitcherReportRequest`.

Two tier-3 types are **reused directly from `pitch_stats.py`** rather than
redefined, since they're already sport-agnostic:
`CustomStat`/`CustomStatsTable` (name/value tile grid -- "overall stats")
and `CustomPitchTypeStat`/`CustomPitchTypeStatsTable` (per-pitch-type
dynamic table -- a hitter's tier-3 pitch-type table is structurally
identical to a pitcher's).

## PDF assembly -- `app/services/report_lab_generator.py`

`PDF_Generator.generate_hitter_report(data, output_path)` builds one PDF's
`elements` list in this order:

1. Header (`generate_header`) -- player photo, name, school logo, date range,
   team, game count. `generate_header`'s positional slots were named for
   pitchers; the last three free-form subtitle slots carry team/games here.
2. "Key Statistics" tile grid (`generate_stats_grid`, from `data.summary`).
3. Spray charts, left/right side-by-side.
4. Batted Ball Profile table, then Plate Discipline table (both via the
   shared `generate_data_table`).
5. **Tier-3 custom elements** -- a school's own flowables, typically a page
   break + its own header (see below). Has to come before steps 6-9 so
   they land on the new page it starts, not trailing the standard content
   above -- same ordering constraint as the pitcher report.
6. Tier-3 **custom stats grid** (`data.custom_stats`, via
   `generate_stats_grid`).
7. Tier-3 **custom charts** (`data.custom_chart_paths`, via
   `add_image_section`) -- stacked full-width, since a school may return any
   number of them, unlike the fixed left/right spray-chart pair. Each is a
   Plotly figure the school's script returned; the browser renders it to a PNG
   for the export (slots `custom_0`, `custom_1`, ... in the order the page showed them).
8. Tier-3 **custom hit-type tables** (`data.custom_hit_type_stats`, via
   `generate_data_table`).
9. Tier-3 **custom pitch-type tables** (`data.custom_pitch_type_stats`, via
   `generate_data_table`).

**Resilience**: the tier-3 custom-elements block is wrapped in `try/except`
that only logs, never re-raises -- a broken school script degrades to "no
custom section" instead of failing the whole report. `hitter_report.py`'s
`custom_*` collectors have the same shape: any exception is caught and
logged, returning `None`.

## Tier 3: school-defined custom stats

Each school may optionally provide
`app/storage/schools/<school_id>/assets/custom_hitter_report.py`. If the
file doesn't exist, the whole tier is skipped silently. If it exists, it's
loaded dynamically via `app/services/custom_report_loader.py` (shared with
the pitcher path) and may define up to five functions:

| Function | Signature | Called from | Purpose |
|---|---|---|---|
| `get_elements` | `(gen: PDF_Generator, data: HitterReportRequest) -> list[Flowable]` | `report_lab_generator._load_custom_hitter_elements` | Raw ReportLab flowables appended directly into the PDF -- typically its own `PageBreak()` + `gen.generate_header(...)`. Receives the live `PDF_Generator`, so it can reuse `gen.player_pfp`, `gen.school_logo`, and `gen`'s other `generate_*` helpers. |
| `get_stats` | `(source: pd.DataFrame, batter_id) -> list[CustomStat]` | `hitter_report.custom_stats_table` | Overall (not broken out by anything) per-hitter stat rows. Wrapped into a `CustomStatsTable`, rendered as a "Custom Stats" tile grid. |
| `get_hit_type_stats` | `(source: pd.DataFrame, batter_id) -> list[CustomHitTypeStatsTable]` | `hitter_report.custom_hit_type_stats_table` | Per-hit-type rows (Ground/Line/Fly/Pop), each carrying a `stats: dict[str, str]`. |
| `get_pitch_type_stats` | `(source: pd.DataFrame, batter_id) -> list[CustomPitchTypeStatsTable]` | `hitter_report.custom_pitch_type_stats_table` | Per-pitch-type rows -- same `CustomPitchTypeStat`/`CustomPitchTypeStatsTable` types the pitcher tier uses. |
| `get_charts` | `(source: pd.DataFrame, batter_id) -> list[CustomChart]` | `hitter_report.custom_charts` | The one capability the pitcher tier doesn't have. Returns `CustomChart(title, figure)` where `figure` is a Plotly `{'data': [...], 'layout': {...}}` -- the page draws it (and re-colors it for dark mode) and the browser renders the PNG the PDF uses, so a script never writes an image file. Build the layout with `plotly_charts.base_layout(...)` and use `plotly_charts.floats(...)` for any numbers (NaN becomes null; a bare NaN isn't valid JSON). Shapes named `'ink'`/`'muted'` follow the theme; any other shape keeps its own color. See `docs/examples/custom_hitter_chart.py` for a worked example. `hitter_report.custom_charts` skips anything that isn't a valid, strict-JSON, reasonably small figure (at most 6 charts), logging why -- including a script still returning the old `(title, path)` tuples. |

All five receive the **same raw TrackMan DataFrame** described under
Aggregation above -- same column names, not a renamed/lowercased schema.
`CustomStat.value` / `CustomHitTypeStat.stats` / `CustomPitchTypeStat.stats`
values are expected to already be display-ready strings (pre-rounded,
`%`-suffixed where relevant) -- no shared `ColumnFormat` machinery applies
to them the way it does for `HitterDisciplineTable`/`BattedBallTable`.

School 1's script
(`app/storage/schools/1/assets/custom_hitter_report.py`) is the worked
example -- unlike the pitcher tier's school-1 script (which has known-buggy
placeholder stats, see the pitching doc's "Known gaps"), every stat it
computes is real: Chase%/Whiff%/Zone Swing%/Damage% overall, a per-hit-type
Hard-Hit%/two-strike-rate table, a per-pitch-type two-strike-whiff%/damage%
table, and an exit-velocity-vs-launch-angle scatter with the barrel zone
shaded.

## Multi-user filename isolation

This pipeline writes no image or PDF files ahead of time any more. A PDF export works in a private
per-request directory (`export_workdir`, prefixed with the requesting user's id) that is removed when the
response is built, so two coaches at the same school exporting the same hitter at the same time can't
collide.
