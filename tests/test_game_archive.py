"""
Service-level tests for app.services.game_archive.

These need no Flask app context -- game_archive takes a games_dir and never touches
request state. That is deliberate: it means the rebuild path can be tested directly.

The contract under test is rebuild_manifest(games_dir) -> int, which re-derives
index.json from the files on disk and returns the number of entries written.
"""
import json
import os
import shutil
from pathlib import Path

import pytest

from app.services import game_archive

FIXTURES = Path(__file__).parent / 'fixtures'
GAME_1 = FIXTURES / 'sample_hitting_game_1.csv'   # 2026-03-01
GAME_2 = FIXTURES / 'sample_hitting_game_2.csv'   # 2026-03-08

BATTER_ID = '500'


@pytest.fixture
def games_dir(tmp_path):
    """An archive holding both fixture games, written by the current code."""
    d = tmp_path / 'games'
    d.mkdir()
    game_archive.archive_game(str(d), str(GAME_1))
    game_archive.archive_game(str(d), str(GAME_2))
    return str(d)


def _manifest(games_dir):
    return game_archive.read_manifest(games_dir)


def _batter(entry, batter_id=BATTER_ID):
    return next(b for b in entry['batters'] if b['id'] == batter_id)


def _make_stale(games_dir):
    """
    Rewrite the manifest the way the pre-schema code did: batters carry only
    id/name/team, and there is no practice flag. This is the state a real archive
    is in after the schema change -- every batter reads batted_balls 0.
    """
    stale = []
    for entry in _manifest(games_dir):
        entry = dict(entry)
        entry.pop('practice', None)
        entry['batters'] = [
            {'id': b['id'], 'name': b['name'], 'team': b['team']}
            for b in entry['batters']
        ]
        stale.append(entry)
    game_archive._write_manifest(games_dir, stale)
    return stale


# --- id stringification ----------------------------------------------------

def test_ids_are_plain_digits_even_when_a_null_id_floats_the_column(tmp_path):
    """
    One null id makes pandas read the whole column as float64, and dropna() does
    not convert it back -- so a naive str() gives '500.0' here and '500' in a
    clean game. The same player would then split into two rows in the pickers.
    """
    import pandas as pd

    df = pd.read_csv(GAME_1)
    # A row with no batter or pitcher id, as an untracked pitch would arrive
    blank = df.iloc[[0]].copy()
    blank['BatterId'] = None
    blank['PitcherId'] = None
    dirty = pd.concat([df, blank], ignore_index=True)

    d = tmp_path / 'games'
    d.mkdir()
    path = d / 'dirty.csv'
    dirty.to_csv(path, index=False)
    assert pd.read_csv(path)['BatterId'].dtype == 'float64', 'fixture should float the column'

    entry = game_archive.archive_game(str(d), str(path))

    assert all('.' not in b['id'] for b in entry['batters']), entry['batters']
    assert BATTER_ID in {b['id'] for b in entry['batters']}
    for key in ('pitchers',):
        assert all('.' not in p['id'] for p in entry.get(key, []))


# --- the bug this exists to fix -------------------------------------------

def test_rebuild_backfills_batted_balls_on_a_stale_manifest(games_dir):
    _make_stale(games_dir)
    assert all('batted_balls' not in b for e in _manifest(games_dir) for b in e['batters'])

    count = game_archive.rebuild_manifest(games_dir)

    assert count == 2
    by_date = {e['date']: e for e in _manifest(games_dir)}
    assert _batter(by_date['2026-03-01'])['batted_balls'] == 3
    assert _batter(by_date['2026-03-08'])['batted_balls'] == 2


def test_rebuild_backfills_the_practice_flag(games_dir):
    _make_stale(games_dir)

    game_archive.rebuild_manifest(games_dir)

    assert all(e.get('practice') is False for e in _manifest(games_dir))


def test_rebuild_makes_hitters_visible_again(games_dir):
    """The end-to-end symptom: batted_only hides everyone until the rebuild runs."""
    _make_stale(games_dir)
    assert game_archive.list_hitters(games_dir, 'HOME', 'own', batted_only=True) == []

    game_archive.rebuild_manifest(games_dir)

    hitters = game_archive.list_hitters(games_dir, 'HOME', 'own', batted_only=True)
    assert next(h for h in hitters if h['id'] == BATTER_ID)['batted_balls'] == 5


# --- must not destroy anything --------------------------------------------

def test_rebuild_never_empties_a_healthy_manifest(games_dir):
    """Regression: rebuilding via archive_game returned None per file and wrote []."""
    before = _manifest(games_dir)
    assert len(before) == 2

    game_archive.rebuild_manifest(games_dir)

    assert len(_manifest(games_dir)) == 2


def test_rebuild_does_not_copy_or_duplicate_files(games_dir):
    before = sorted(os.listdir(games_dir))

    game_archive.rebuild_manifest(games_dir)

    assert sorted(os.listdir(games_dir)) == before


def test_rebuild_is_idempotent(games_dir):
    game_archive.rebuild_manifest(games_dir)
    once = _manifest(games_dir)

    game_archive.rebuild_manifest(games_dir)

    assert _manifest(games_dir) == once


def test_rebuild_preserves_an_existing_practice_flag(tmp_path):
    """practice is a human choice at upload time and is not recoverable from the file."""
    d = tmp_path / 'games'
    d.mkdir()
    game_archive.archive_game(str(d), str(GAME_1), practice=True)
    game_archive.archive_game(str(d), str(GAME_2), practice=False)

    game_archive.rebuild_manifest(str(d))

    by_date = {e['date']: e for e in _manifest(str(d))}
    assert by_date['2026-03-01']['practice'] is True
    assert by_date['2026-03-08']['practice'] is False


# --- repairs it should perform --------------------------------------------

def test_rebuild_indexes_a_file_missing_from_the_manifest(games_dir):
    """A file present on disk but absent from the index gets picked up."""
    entries = _manifest(games_dir)
    orphan = entries[0]['file']
    game_archive._write_manifest(games_dir, entries[1:])

    count = game_archive.rebuild_manifest(games_dir)

    assert count == 2
    assert orphan in {e['file'] for e in _manifest(games_dir)}


def test_rebuild_drops_an_entry_whose_file_is_gone(games_dir):
    entries = _manifest(games_dir)
    os.remove(os.path.join(games_dir, entries[0]['file']))

    count = game_archive.rebuild_manifest(games_dir)

    assert count == 1
    assert entries[0]['file'] not in {e['file'] for e in _manifest(games_dir)}


def test_rebuild_ignores_non_game_files(games_dir):
    """index.json lives here, and an interrupted _write_manifest leaves .tmp behind."""
    Path(games_dir, 'leftover.tmp').write_text('not a game')
    Path(games_dir, 'notes.txt').write_text('also not a game')

    count = game_archive.rebuild_manifest(games_dir)

    assert count == 2
    assert all(e['file'].endswith(('.csv', '.xlsx', '.xls')) for e in _manifest(games_dir))


def test_rebuild_sorts_entries_by_date(games_dir):
    game_archive.rebuild_manifest(games_dir)

    dates = [e['date'] for e in _manifest(games_dir)]
    assert dates == sorted(dates)


def test_rebuild_on_an_empty_directory_returns_zero(tmp_path):
    d = tmp_path / 'games'
    d.mkdir()

    assert game_archive.rebuild_manifest(str(d)) == 0
    assert _manifest(str(d)) == []


# --- entries stay equivalent to what archive_game writes -------------------

def test_rebuilt_entries_match_freshly_archived_ones(games_dir, tmp_path):
    """
    A rebuilt entry and a freshly archived one must be identical, or the two code
    paths have drifted -- the reason both should call the same builder.
    """
    fresh = _manifest(games_dir)
    game_archive.rebuild_manifest(games_dir)
    rebuilt = _manifest(games_dir)

    assert rebuilt == fresh
