# app/routes

Flask blueprints. School-scoping and auth live here — see root CLAUDE.md's Key Rules.

## Report pages: filtered, Plotly-drawn reports (pitching.py, batting.py, catching.py)

All three pages follow one shape, built in-process (no worker pool anywhere):

- `POST /api/<page>/report` streams NDJSON: a `meta` line (filter-bar contents + the chart
  defaults), one `report` card per pitcher/hitter/catcher, then `done`. Cards carry stat-table
  HTML and Plotly *figure specs* -- no chart PNGs, no PDFs are built there.
- `POST /api/<page>/pitcher|hitter|catcher` rebuilds one card for new filters/chart options
  (`charts_only` skips the tables).
- `POST /api/<page>/export` builds the PDF on demand: it recomputes every number from the
  school's archive and takes only the filters (validated by `PitchFilters.from_request`) and the
  browser-rendered chart PNGs (validated by `chart_images.save_chart_image`) from the client.
  Each export works in its own `utils.export_workdir` and returns the PDF from memory.
- Pitch-by-pitch PDFs are GET links built on request (vector at-bat panels, so they are cheap);
  they carry the filters as a JSON `filters` query param (`utils.filters_from_args`).

Every route that reads games applies `PitchFilters.apply(source)` once, right after loading, so
tables, charts, custom scripts and the pitch-by-pitch PDFs all see the same pitches. Games load
through `game_archive.load_games_cached` / `load_range_cached` (last 2 selections; the frame is
shared, so never mutate it). Account defaults and shared helpers live in `routes/utils.py`
(`chart_prefs`, `charts_enabled`, `export_workdir`).

Don't read `current_user` inside `app/services` -- `_card_payload` and the export views read it in
the view layer and pass plain values down.

Colors: hitter spray charts color "velocity" by *exit* velocity; the catcher page adds `framing`
and defaults to it regardless of the account's pitch-type/velocity setting.

Frontend side: `report_cards.js` (`createReportCards`) owns the cards on all three pages --
filter refresh, Plotly drawing, client-side PNG export -- and each page supplies only its own
endpoints and how a card's tables are filled in. `readNdjson(response)` in `core.js` is the shared
async generator the pages use to read the streamed body — reuse it rather than
writing another NDJSON reader if a third route ever streams results the same way.
