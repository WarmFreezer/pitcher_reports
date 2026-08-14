# Test Plan: School Slug → School ID Migration

## Goal

`School.slug` (`app/db/models.py:12`, currently `db.Column(db.String(50), unique=True, nullable=False)`)
is used two ways today:

1. As an **internal identifier** — Stripe webhook metadata (`app/routes/payments.py:45`,
   `app/routes/subscription.py:111`), CLI school resolution (`app/cli.py`'s `create_user`), and, most
   importantly, as the **on-disk storage directory key** (`storage/schools/{slug}/...`) for every
   school's branding, logos, rosters, temp files, PDF reports, and archived games.
2. As a **display value** — shown in list output, page titles, and the school signup form.

The goal of this migration is to eliminate use (1) entirely — replace it everywhere with `school.id`
— so that `slug` can become a display-only field and its `unique=True` DB constraint can be dropped.

## Why this needs a test plan before code changes

`slug` is not a foreign key anywhere (verified: no `ForeignKey('schools.slug')` exists in the schema),
so dropping the DB constraint is safe from a *relational* standpoint. The real risk is the **storage
layer**, which today assumes "one slug = one school" implicitly, by using the slug as a directory name.
If the unique constraint is dropped before storage paths are switched to `school.id`, two schools that
end up with the same slug will silently read and write into the *same* directory — branding, logos,
rosters, temp uploads, PDF reports, and archived game data would leak across school boundaries. That is
a direct violation of the CLAUDE.md invariant *"never return data across school boundaries"*, and
`tests/test_school_isolation.py` already exists specifically to guard that invariant.

So the test plan exists to (a) pin the current, correct behavior before anything changes, (b) define
the target behavior the migration must reach, and (c) make the one dangerous failure mode — slug
collision causing storage crossover — impossible to ship unnoticed.

## Test categories

### A. Baseline regression

Confirm `pytest -q --cov=app` is green on current `main` before any migration code lands. This is the
existing CI gate (`.github/workflows/test.yml`); no new test needed, just a checkpoint.

### B. Storage-path collision safety (the critical new coverage)

Two schools with an **identical slug** must resolve to **distinct** storage directories once paths are
keyed by `school.id` instead of `school.slug`.

- Extend `tests/conftest.py`'s `make_school` fixture usage (it already generates
  `slug=f'test-school-{n}'` via a uid counter) with a new `two_schools_same_slug` fixture in
  `tests/test_school_isolation.py` that forces both schools to share one slug.
- New test: seed a games-archive `index.json` for School B (same pattern
  `test_batting_hitters_only_lists_own_schools_archive` / `test_pitching_games_only_lists_own_schools_archive`
  already use), confirm School A's user still sees zero games from B — *even when both schools have the
  same slug*. This is the collision case the existing two tests don't cover (they use distinct
  auto-generated slugs today).
- Update the two existing tests above: they currently build `games_dir` via `school.slug`
  (`test_school_isolation.py:78,113`) — once storage is keyed by id, they must build it via `school.id`
  instead, or they'll silently stop testing the real path and pass for the wrong reason.
- `BrandingLoader.get_branding`/`get_logo_path`/`create_school_dir`/`update_branding` — add a direct
  unit test creating two same-slug schools and confirming their branding files land in and load from
  separate directories.

### C. DB-lookup call-site migration

- `app/routes/payments.py:45` — the Stripe resubscribe webhook currently does
  `School.query.filter_by(slug=metadata['school_slug']).first()`. Target: resolve by `school_id` from
  Stripe metadata instead. Test: webhook resolves the correct school when two schools share a slug (this
  is untestable meaningfully *today* only because slug is unique — once uniqueness is relaxed, this
  test is what proves the webhook didn't silently keep the old ambiguous lookup).
- `app/routes/subscription.py:111` — sets the Stripe metadata the webhook reads; test that the metadata
  key changes from `school_slug` to `school_id` and the resubscribe flow still round-trips correctly
  (`mock_stripe` fixture already supports this).
- `app/cli.py`'s `create_user` command currently does `School.query.filter_by(slug=school_slug).first()`
  (`cli.py:151`) after prompting for a slug. Target: resolve by school id (mirroring `list-schools`'
  existing `f'{school.id}. {school.name} ({school.slug})'` display at `cli.py:113`). CLI commands using
  `input()` aren't directly pytest-friendly today (no existing test coverage for them) — cover the
  *resolution logic* by extracting it into a small testable helper (e.g.
  `resolve_school_by_id(school_id: int) -> School | None`) rather than trying to test the `input()`
  prompts themselves.

### D. One-time storage migration script

A new idempotent script/CLI command moves existing `storage/schools/{slug}/` directories to
`storage/schools/{id}/` for each `School` row (needed because deployed data, including this repo's own
local `app/storage/schools/{BU,UK,def,msu,mwc,test}/` directories, is already slug-keyed).

- Given a slug-keyed directory and a matching `School` row, the script moves it to the id-keyed path.
- Idempotent: running it a second time is a no-op (source no longer exists after the first run).
- Safe: if the id-keyed destination already exists, the script must not overwrite/clobber it (guards
  against a partially-migrated environment being re-run incorrectly).
- No-op cleanly when there's nothing to migrate (fresh environment with only id-keyed data).

### E. Alembic migration — drop the unique constraint

New revision (there is currently no prior revision touching `schools` — `School`/`User` were only ever
created via `db.create_all()`, so this is a from-scratch migration, not an alter of an existing one).
Follow the cross-DB-safe `Inspector`-based conditional pattern already used in
`migrations/versions/95218ed0478e_rm_content_hash_restrictions.py` (SQLite and Postgres name/store
unique constraints differently, so the constraint name must be introspected, not hardcoded blindly).

- After `upgrade()`, creating two `School` rows with the same slug must succeed (no `IntegrityError`).
- `downgrade()` should restore the constraint (and should fail/warn if duplicate slugs already exist at
  that point — acceptable to document as a known downgrade limitation rather than solve automatically).

### F. Full-suite re-run

Once B–E land, re-run the *entire* existing suite (not just the new/changed tests) to catch anything
that implicitly depended on slug uniqueness or slug-keyed paths that wasn't already flagged above.

## Sequencing this test plan pins

The tests above are written to enforce this deployment order (see the plan file for full rationale):

1. Storage-path builders switch to `school.id` while `slug` is *still unique* (zero risk — one slug
   still maps to exactly one id at this point).
2. Run the one-time migration script against real storage.
3. Verify (test suite + manual spot check).
4. Drop the unique constraint (Alembic migration).
5. Switch the remaining DB-lookup call sites (webhook metadata, CLI) in the same wave as step 4.

Category B tests are what make it unsafe to skip step 1, and category E tests are what make it possible
to safely execute step 4 only once B–D are proven.

## Where these tests live

| Category | File |
|---|---|
| A | existing CI (`pytest -q --cov=app`) — no new file |
| B | `tests/test_school_isolation.py` (extends existing fixtures/tests) |
| C | `tests/test_slug_migration.py` (new) |
| D | `tests/test_storage_migration_script.py` (new) |
| E | `tests/test_slug_migration.py` (new, same file as C) |
| F | existing CI, run as-is |
