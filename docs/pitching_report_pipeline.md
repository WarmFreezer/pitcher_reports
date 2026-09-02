# Pitching Report Pipeline

## Overview

A pitcher report goes through four stages, each in its own module:

1. **Selection & orchestration** — `app/routes/pitching.py`. Resolves which
   TrackMan rows belong to the request, loops over each pitcher, and calls
   the next three stages.
2. **Aggregation** — `app/services/report.py`. Turns raw per-pitch TrackMan
   rows into per-pitcher/per-pitch-type numbers (pandas `groupby`-style
   aggregation, never done row-by-row in Python per `CLAUDE.md`).
3. **Typed value objects** — `app/services/pitch_stats.py` +
   `app/services/stat_table.py`. The aggregation results are packaged into
   dataclasses/`StatTable`s instead of DataFrames, so formatting is declared
   once per column instead of re-derived by every consumer.
4. **PDF assembly** — `app/services/report_lab_generator.py`. `PDF_Generator`
   takes one `PitcherReportRequest` and lays out a ReportLab PDF from it.

A fifth, optional stage — **tier-3 custom stats** — lets an individual school
inject its own stats/flowables into stage 2-4 via a Python file the school
owns. See the dedicated section below.

## Entry point: `app/routes/pitching.py`

The export route resolves a date range and set of games into a single
`source` DataFrame (already filtered to `current_user.school_id` per the
school-scoping invariant in `CLAUDE.md`), then loops
`matching['PitcherId'].unique()`. For each pitcher it:

1. If `current_user.school.is_active` (the paid/tier-gated flag): renders
   heat maps and a break map (`report.pitch_heat_map_by_batter_side()`,
   `report.pitch_break_map()`), then collects tier-3 custom stats
   (`report.custom_stats_table()`, `report.custom_pitch_type_stats_table()`).
2. Unconditionally: `report.build_table()` for the per-pitch-type stats table
   and `report.usage_table()` for the pitch-usage-by-count tables.
3. Assembles all of the above into one `PitcherReportRequest` and calls
   `PDF_Generator.generate_pitcher_report()`.

Each pitcher is wrapped in its own `try/except` — one pitcher failing doesn't
stop the rest of the batch from exporting.

## The strike zone — `app/services/report_theme.py`

The rulebook strike zone is defined once, in feet of plate location, and
everything else reads from these constants instead of repeating the numbers:

```python
ZONE_SIDE = 0.83    # half-width, so the zone spans -0.83 to 0.83
ZONE_BOTTOM = 1.5
ZONE_TOP = 3.5
```

- `in_zone(plate_loc_side, plate_loc_height)` / `out_of_zone(...)` — vectorized
  boolean masks over `PlateLocSide`/`PlateLocHeight`. Both accept a `pd.Series`
  or a scalar. **NaN locations fall out as `False` for `in_zone` and `True`
  for `out_of_zone`** — an untracked pitch is treated as not-a-strike, never
  as evidence of one.
- `make_strike_zone()` draws the same box as a dashed `Rectangle` for
  heatmap/break-map plots — the constants above are the single source of
  truth, so the drawn box and the in/out-zone math can't drift apart.
- **Shadow zone**: `baseball_width = 0.24` ft (one ball-width) padding
  outside the rulebook zone, drawn by `make_shadow_zone()` as a dotted
  outline. This is a *visual* borderline-pitch indicator only — it is not
  read by any `in_zone`/`out_of_zone` call, so nothing currently treats a
  shadow-zone pitch as a strike.
- `make_homeplate()` draws home plate at the front of the zone purely for
  orientation in heatmap plots.

Every consumer of zone logic — `report.build_table()`'s chase% calculation,
`report.py`'s heat maps, and a school's own `custom_pitcher_report.py` (see
below) — imports `in_zone`/`out_of_zone` from here rather than re-deriving
the bounds.

## Aggregation — `app/services/report.py`

Raw rows are expected to carry the TrackMan columns listed in
`required_columns` (`report.py:48-76`) — notably `PitcherId`,
`TaggedPitchType`, `PlateLocSide`/`PlateLocHeight`, `PitchCall`, `Balls`,
`Strikes`, `RelSpeed`, and the movement/release columns. Four functions do
the real aggregation, all pushing `sum`/`mean`/`isin` down to pandas rather
than looping in Python:

- **`build_table(source, pitcher_id)`** — per-pitch-type stats: velocity,
  movement, release point, zone%, chase% (out-of-zone + swung), CSW% (called
  strike + whiff), and tilt (parsed from a clock-face string tried against
  four possible TrackMan export formats). Keeps the top 6 most-thrown pitch
  types via `_top_pitches()`, then reorders them into the canonical
  `pitch_order` from `report_theme.py`. Returns a `PitcherGameReport`.
- **`pitch_heat_map_by_batter_side(...)`** — KDE location heatmaps, one image
  per batter side (`Left`/`Right`) and theme (`light`/`dark`), saved as PNGs.
- **`pitch_break_map(...)`** — induced-vertical-break vs. horizontal-break
  KDE plot; also returns the pitcher's overall arm angle.
- **`usage_table(source, pitcher_id)`** — pitch usage broken out by count
  situation (first pitch, hitter-favorable, pitcher-favorable, 2-strike),
  split by batter side, returned as `PitchUsageSides(left, right)`.

## Typed value objects — `stat_table.py` + `pitch_stats.py`

`StatTable[RowT]` (`app/services/stat_table.py`) pairs an ordered list of
dataclass rows with a `columns: list[Column]` spec. Each `Column` names the
row field it reads, its header text, and a `ColumnFormat`
(`PERCENT`/`DECIMAL0`/`DECIMAL1`/`DECIMAL2`/`INT`/`TEXT`) — the formatting
rule for a value is declared once, instead of every consumer re-deriving it
via `isinstance`/column-name checks the way a raw DataFrame required.
`to_reportlab_rows()`, `to_dict()`, and `to_html()` all read off the same
spec.

`app/services/pitch_stats.py` defines the concrete tables:

- `PitcherStatsTable` (17 columns) / `PitchUsageTable` (8 columns) — fixed
  schema, backing `build_table()`/`usage_table()`.
- `CustomStatsTable` / `CustomPitchTypeStatsTable` — the tier-3 tables (see
  below). `CustomPitchTypeStatsTable` is the one exception to "fixed
  schema": its headers are derived at runtime from the union of each row's
  `stats` dict keys (since a custom script can add whatever stat names it
  wants), and it carries a `title` and an optional `col_widths` for the
  renderer.
- `PitcherReportRequest` — the single struct `PDF_Generator.generate_pitcher_report()`
  takes, replacing an older ad hoc dict that mixed strings, DataFrames, and
  image paths and needed defensive `isinstance()` checks everywhere it was read.

## PDF assembly — `app/services/report_lab_generator.py`

`PDF_Generator.generate_pitcher_report(data, output_path)` builds one PDF's
`elements` list in this order:

1. Header (`generate_header`) — player photo, name, school logo, game info.
2. Heat maps, left/right side-by-side (if present).
3. Break map + usage tables side-by-side, or usage tables alone if there's
   no break map.
4. Pitch stats table (`generate_pitcher_stats_table`, from `data.pitch_stats`).
5. **Tier-3 custom elements** — a school's own flowables, typically a page
   break + its own header (see below). This has to come *before* step 6 so
   the custom stats tables land on the new page it starts, not trailing the
   standard content above.
6. Tier-3 **custom stats grid** (`data.custom_stats`, rendered via
   `generate_stats_grid`).
7. Tier-3 **custom pitch-type tables** (`data.custom_pitch_type_stats`,
   rendered via `generate_data_table`).

Two shared renderers back most of this:

- **`generate_data_table(table, title, available_width=None, col_widths=None)`**
  — generic `StatTable` renderer. Column widths resolve in priority order:
  the `col_widths` argument, then a `col_widths` attribute set on the table
  object itself, then an even split of `available_width`. Column *count*
  comes from the rendered header row (`table.to_reportlab_rows()[0]`), not
  `table.columns` — required because `CustomPitchTypeStatsTable` leaves the
  static `columns` classvar empty.
- **`generate_stats_grid(stats_data, title="Key Statistics")`** — a 4-per-row
  tile grid (big value over a label), used for both the hitter report's "Key
  Statistics" and the pitcher report's "Custom Stats". Padding cells (when
  the stat count isn't a multiple of 4) must be empty `Paragraph`s, not raw
  strings — ReportLab treats a list-valued cell as stacked flowables and
  calls `.wrapOn()` on each item, which raw strings don't have.

**Resilience**: the tier-3 custom-elements block is wrapped in `try/except`
that only logs, never re-raises — a broken school script degrades to "no
custom section" instead of failing the whole report. `report.py`'s
`custom_stats_table()`/`custom_pitch_type_stats_table()` collectors have the
same shape: any exception is caught and logged, returning `None`.

## Tier 3: school-defined custom stats

Each school may optionally provide
`app/storage/schools/<school_id>/assets/custom_pitcher_report.py`. If the
file doesn't exist, the whole tier is skipped silently — no error, no empty
section. If it exists, it's loaded dynamically via `importlib` (once in
`report.py`, once more in `report_lab_generator.py` — each load re-execs the
file, they are not sharing a cached module) and may define up to three
functions:

| Function | Signature | Called from | Purpose |
|---|---|---|---|
| `get_elements` | `(gen: PDF_Generator, data: PitcherReportRequest) -> list[Flowable]` | `report_lab_generator._load_custom_elements` | Raw ReportLab flowables appended directly into the PDF — typically its own `PageBreak()` + `gen.generate_header(...)` to start a fresh page. Receives the live `PDF_Generator` instance, so it can reuse `gen.player_pfp`, `gen.school_logo`, and any of `gen`'s other `generate_*` helpers. |
| `get_stats` | `(source: pd.DataFrame, pitcherId: int) -> list[CustomStat]` | `report.custom_stats_table` | Raw per-pitcher stat rows. Wrapped into a `CustomStatsTable` and rendered as the "Custom Stats" tile grid. |
| `get_pitch_type_stats` | `(source: pd.DataFrame, pitcher_id: int) -> list[CustomPitchTypeStat]` | `report.custom_pitch_type_stats_table` | Raw per-pitch-type stat rows (one `CustomPitchTypeStat` per pitch type, each carrying a `stats: dict[str, str]`). Wrapped into `[CustomPitchTypeStatsTable(rows)]` and rendered as a normal table. |

All three receive the **same raw TrackMan DataFrame** described under
Aggregation above — same column names (`PitcherId`, `TaggedPitchType`,
`PlateLocSide`/`PlateLocHeight`, `PitchCall`, `Angle`, `RelSpeed`, `Balls`,
`Strikes`, ...), not a renamed or lowercased schema. `CustomStat.value` and
`CustomPitchTypeStat.stats` values are expected to already be display-ready
strings (pre-rounded, `%`-suffixed where relevant) — there is no shared
`ColumnFormat` machinery applied to them the way there is for
`PitcherStatsTable`/`PitchUsageTable`.

School 1's script (`app/storage/schools/1/assets/custom_pitcher_report.py`)
is the only one in the repo today and is a useful worked example — it
defines an `early_execution()` helper (percentage of 0-0/0-1/1-0/1-1-count
pitches thrown in the zone) that both `get_stats` and `get_pitch_type_stats`
call into.

## Known gaps (as of writing)

- Several stats are still hardcoded placeholders pending a real calculation:
  pitcher-level Early/Late Execution, Putaway, R2K, Non-Competitive
  (`custom_pitcher_report.py:68-72`), and pitch-type-level Overall
  Execution/Late Execution/zone-location (`custom_pitcher_report.py:112-118`).
- `custom_pitcher_report.py:134-136` reads an undefined `zone_location` name
  — the single `zone_location` variable was split into
  `inner_zone_location`/`middle_zone_location`/`outer_zone_location`
  (`:116-118`) but the three dict entries weren't updated to match. This
  raises `NameError` inside `get_pitch_type_stats()`; it's caught by
  `report.custom_pitch_type_stats_table()`'s `try/except`, so today it just
  means the custom pitch-type table silently doesn't render rather than
  crashing the report.
- Some computed ratios (e.g. Swing Decision, Ground Ball%) can read over
  100% because the numerator and denominator aren't always drawn from
  matching pitch subsets — a stat-correctness issue, not a wiring one.
