# app/routes

Flask blueprints. School-scoping and auth live here — see root CLAUDE.md's Key Rules.

## Streamed, parallel report building (pitching.py, batting.py)

`/api/pitching/report` and `/api/batting/report` build every pitcher's/hitter's report
in a `ProcessPoolExecutor` and stream results back as newline-delimited JSON (one
`{"type": "report", ...}` line per pitcher/hitter as their report finishes, then one
`{"type": "done", ...}` line with the merged-PDF URL and run summary) via
`Response(stream_with_context(...), mimetype='application/x-ndjson')`.

The per-pitcher/per-hitter worker (`_build_one_pitcher_report` / `_build_one_hitter_report`)
runs in a **separate process** — it must be a module-level function (picklable, importable
by the spawned/forked child) and must not touch `current_user`, `db.session`, `session`,
`request`, or anything else tied to Flask's app/request context. Resolve everything the
worker needs (ids, folder paths, the user's `chart_style`/`ink_mode`, branding dict,
pre-fetched DB lookups like pitcher height/weight/age) in the view function first, and
hand it over as a plain dict via `executor.submit(worker_fn, task_dict)`. If a future
change needs something from the DB per-pitcher, fetch it for every pitcher up front in
the view function (see `pitcher_meta_by_id` in `pitching.py`) rather than querying inside
the worker.

`source` (the full multi-pitcher/both-teams DataFrame) is passed whole to every task
rather than pre-filtered to one pitcher's rows, deliberately matching what the
old sequential loop passed into these same `report.py`/`hitter_report.py` functions —
some of them read from unfiltered `source` (e.g. `build_table`'s `source['BatterTeam'].iloc[0]`),
so filtering down without auditing every callee first would risk silently changing
behavior. This does mean `source` gets pickled once per task; if that ever becomes a real
bottleneck, that's the place to optimize, not by guessing at which rows are safe to drop.

Frontend side: `readNdjson(response)` in `core.js` is the shared async generator both
`pitching.js` and `batting.js` use to read the streamed body — reuse it rather than
writing another NDJSON reader if a third route ever streams results the same way.
