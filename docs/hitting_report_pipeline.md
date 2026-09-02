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

`batting_report()` resolves a date range, loads every archived game inside
it into a single `source` DataFrame (school-scoped per the invariant in
`CLAUDE.md`), then loops the requested `batter_ids`. For each hitter it:

1. If `current_user.school.is_active` (the paid/tier-gated flag): renders
   spray charts (`hitter_report.hitter_spray_chart_by_pitcher_side()`), then
   collects tier-3 custom stats/hit-type stats/pitch-type stats/charts
   (`hitter_report.custom_stats_table()`,
   `custom_hit_type_stats_table()`, `custom_pitch_type_stats_table()`,
   `custom_charts()`).
2. Unconditionally: `hitter_report.build_hitter_summary()`,
   `build_hitter_discipline_table()`, `build_batted_ball_table()`.
3. Assembles all of the above into one `HitterReportRequest` and calls
   `PDF_Generator.generate_hitter_report()`.

Each hitter is wrapped in its own `try/except` -- one hitter failing doesn't
stop the rest of the batch, matching `pitching.py`'s loop.

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
- **`hitter_spray_chart_by_pitcher_side(...)`** -- landing-spot scatter
  colored by exit velocity, one image per pitcher side (`Left`/`Right`) and
  theme, built from `Bearing`/`Distance` (TrackMan leaves
  `PitchLastMeasuredX/Z` empty, so those aren't usable here).

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
   number of them, unlike the fixed left/right spray-chart pair.
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
| `get_charts` | `(source: pd.DataFrame, batter_id, user_id: int, output_dir: str) -> list[tuple[str, str]]` | `hitter_report.custom_charts` | The one capability the pitcher tier doesn't have. The school's script does its own matplotlib rendering from the raw rows and saves PNG(s) into `output_dir`, returning `(title, path)` pairs. `user_id` is passed through (not just `batter_id`) so the script can namespace filenames the way every built-in temp file in this app already does -- prefixed by the requesting user's id, so two coaches at the same school generating reports for the same batter concurrently can't clobber each other's output. |

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

Every temp file this pipeline writes -- built-in spray charts and tier-3
custom charts alike -- is prefixed by the *requesting user's* id, not just
the batter's: `{user_id}_hitter_{batter_id}_...`. Two coaches at the same
school can generate reports for the same batter at the same time without
overwriting each other's PNGs, and `batting_report()`'s stale-file cleanup
glob (`{current_user.id}_hitter_*_spray_*.png` /
`{current_user.id}_hitter_*_custom_*.png`) only ever clears the requesting
user's own prior output.
