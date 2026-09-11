# app/services

Report-building and business logic. Pure Python/pandas — no Flask, no `current_user`,
no `db.session` in this folder (verified across `report.py`, `hitter_report.py`,
`pitch_stats.py`, `hitter_stats.py`, `report_lab_generator.py`, `custom_report_loader.py`).
Keep it that way: `app/routes/pitching.py` and `app/routes/batting.py` run per-pitcher/
per-hitter report building in a `ProcessPoolExecutor`, so anything in here that started
depending on Flask's app/request context would break silently in a worker process
(no error at import time — it fails the first time the code path actually runs).

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

Hitter side additionally supports `get_hit_type_stats` and `get_charts`. Every call site
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
