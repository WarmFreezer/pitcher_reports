"""
Spec for Phase B's service layer: game listing, deletion, and the practice flag.

Written against game_archive directly -- no Flask app context needed, same as
test_game_archive.py. The routes in app/routes/pitching.py consume exactly these
contracts, so green here means the seam is closed.

Fixture games, both HOME vs AWAY with HOME as the home team:
    sample_hitting_game_1.csv  2026-03-01
    sample_hitting_game_2.csv  2026-03-08
"""
import os
from pathlib import Path

import pytest

from app.services import game_archive

FIXTURES = Path(__file__).parent / 'fixtures'
GAME_1 = FIXTURES / 'sample_hitting_game_1.csv'   # 2026-03-01
GAME_2 = FIXTURES / 'sample_hitting_game_2.csv'   # 2026-03-08

HOME = 'HOME'
AWAY = 'AWAY'


@pytest.fixture
def games_dir(tmp_path):
    d = tmp_path / 'games'
    d.mkdir()
    game_archive.archive_game(str(d), str(GAME_1))
    game_archive.archive_game(str(d), str(GAME_2))
    return str(d)


def _by_date(games):
    return {g['date']: g for g in games}


# --- list_games: the /pitching checkbox list -------------------------------

def test_list_games_returns_one_row_per_archived_game(games_dir):
    games = game_archive.list_games(games_dir, HOME)

    assert len(games) == 2
    assert [g['date'] for g in games] == ['2026-03-01', '2026-03-08']


def test_list_games_row_carries_everything_the_checkbox_needs(games_dir):
    game = game_archive.list_games(games_dir, HOME)[0]

    # content_hash is the identity used by delete and by report generation
    assert set(game) >= {
        'content_hash', 'date', 'label', 'opponent', 'practice',
        'pitcher_count', 'batter_count',
    }
    assert game['content_hash']
    assert game['practice'] is False


def test_list_games_labels_home_and_away_from_the_schools_perspective(games_dir):
    """
    HOME is the home team in both fixtures, so HOME sees a home label and AWAY
    sees an away one. Asserted on the distinction rather than the exact wording --
    'vs.' vs '@' vs 'at' is a display choice that should be free to change.
    """
    home_view = game_archive.list_games(games_dir, HOME)
    away_view = game_archive.list_games(games_dir, AWAY)

    assert all('vs' in g['label'].lower() for g in home_view)
    assert all('vs' not in g['label'].lower() for g in away_view)
    # whichever wording, the row has to name who it was against
    assert all(g['opponent'] in g['label'] for g in home_view + away_view)


def test_list_games_names_the_other_team_as_opponent(games_dir):
    home_view = game_archive.list_games(games_dir, HOME)
    away_view = game_archive.list_games(games_dir, AWAY)

    assert {g['opponent'] for g in home_view} == {AWAY}
    assert {g['opponent'] for g in away_view} == {HOME}


def test_list_games_counts_participants(games_dir):
    """Counts come from the manifest, not from reopening the CSV."""
    game = _by_date(game_archive.list_games(games_dir, HOME))['2026-03-01']

    # Doe pitches for HOME, Smith for AWAY
    assert game['pitcher_count'] == 2
    # Zulu + Yankee (AWAY) and Alpha + Bravo (HOME)
    assert game['batter_count'] == 4


def test_list_games_honors_the_date_range(games_dir):
    narrowed = game_archive.list_games(
        games_dir, HOME, start_date='2026-03-08', end_date='2026-03-08')

    assert [g['date'] for g in narrowed] == ['2026-03-08']


def test_list_games_on_an_empty_archive_returns_nothing(tmp_path):
    d = tmp_path / 'games'
    d.mkdir()

    assert game_archive.list_games(str(d), HOME) == []


# --- practice flag ---------------------------------------------------------

def test_archived_practice_game_is_flagged(tmp_path):
    d = tmp_path / 'games'
    d.mkdir()
    game_archive.archive_game(str(d), str(GAME_1), practice=True)

    assert game_archive.list_games(str(d), HOME)[0]['practice'] is True


def test_practice_games_are_listed_by_default(tmp_path):
    """They stay reportable -- the flag only gates the database write."""
    d = tmp_path / 'games'
    d.mkdir()
    game_archive.archive_game(str(d), str(GAME_1), practice=True)
    game_archive.archive_game(str(d), str(GAME_2), practice=False)

    assert len(game_archive.list_games(str(d), HOME)) == 2


def test_practice_games_can_be_excluded(tmp_path):
    d = tmp_path / 'games'
    d.mkdir()
    game_archive.archive_game(str(d), str(GAME_1), practice=True)
    game_archive.archive_game(str(d), str(GAME_2), practice=False)

    real = game_archive.list_games(str(d), HOME, include_practice=False)

    assert [g['date'] for g in real] == ['2026-03-08']
    assert all(g['practice'] is False for g in real)


def test_practice_flag_survives_a_rebuild(tmp_path):
    """It is a human choice at upload time and cannot be re-derived from the file."""
    d = tmp_path / 'games'
    d.mkdir()
    game_archive.archive_game(str(d), str(GAME_1), practice=True)

    game_archive.rebuild_manifest(str(d))

    assert game_archive.list_games(str(d), HOME)[0]['practice'] is True


# --- load_games: reading an explicit selection -----------------------------

def test_load_games_reads_only_the_requested_hashes(games_dir):
    """
    The /pitching page selects games with checkboxes, so the loader has to take an
    explicit set. load_range cannot express "these two of the five in this window".
    """
    target = _by_date(game_archive.list_games(games_dir, HOME))['2026-03-08']

    frame = game_archive.load_games(games_dir, [target['content_hash']])

    assert set(frame['GameDate'].unique()) == {'2026-03-08'}


def test_load_games_concatenates_a_multi_game_selection(games_dir):
    hashes = [g['content_hash'] for g in game_archive.list_games(games_dir, HOME)]

    frame = game_archive.load_games(games_dir, hashes)

    assert set(frame['GameDate'].unique()) == {'2026-03-01', '2026-03-08'}


def test_load_games_ignores_unknown_hashes(games_dir):
    frame = game_archive.load_games(games_dir, ['not-a-real-hash'])

    assert frame.empty


def test_load_games_with_no_selection_is_empty(games_dir):
    assert game_archive.load_games(games_dir, []).empty


# --- remove_game -----------------------------------------------------------

def test_remove_game_deletes_the_file_and_the_entry(games_dir):
    target = game_archive.list_games(games_dir, HOME)[0]
    filename = _by_date(game_archive.read_manifest(games_dir))[target['date']]['file']

    removed = game_archive.remove_game(games_dir, target['content_hash'])

    assert removed is True
    assert not os.path.exists(os.path.join(games_dir, filename))
    assert target['content_hash'] not in {
        e['content_hash'] for e in game_archive.read_manifest(games_dir)
    }


def test_remove_game_leaves_the_other_games_alone(games_dir):
    target = game_archive.list_games(games_dir, HOME)[0]

    game_archive.remove_game(games_dir, target['content_hash'])

    remaining = game_archive.list_games(games_dir, HOME)
    assert len(remaining) == 1
    assert os.path.exists(os.path.join(
        games_dir, game_archive.read_manifest(games_dir)[0]['file']))


def test_remove_game_with_an_unknown_hash_is_a_no_op(games_dir):
    removed = game_archive.remove_game(games_dir, 'not-a-real-hash')

    assert removed is False
    assert len(game_archive.read_manifest(games_dir)) == 2


def test_removed_game_drops_out_of_hitter_listings(games_dir):
    """Deleting a game must not leave its hitters behind in the batting picker."""
    before = game_archive.list_hitters(games_dir, HOME, 'own')
    alpha_before = next(h for h in before if h['name'] == 'Alpha, Adam')
    assert alpha_before['games'] == 2

    target = _by_date(game_archive.list_games(games_dir, HOME))['2026-03-01']
    game_archive.remove_game(games_dir, target['content_hash'])

    after = game_archive.list_hitters(games_dir, HOME, 'own')
    alpha_after = next(h for h in after if h['name'] == 'Alpha, Adam')
    assert alpha_after['games'] == 1
    assert alpha_after['batted_balls'] == 2      # only game two's remain


def test_removed_game_drops_out_of_load_range(games_dir):
    target = _by_date(game_archive.list_games(games_dir, HOME))['2026-03-01']
    game_archive.remove_game(games_dir, target['content_hash'])

    frame = game_archive.load_range(games_dir, '2000-01-01', '2100-01-01')

    assert set(frame['GameDate'].unique()) == {'2026-03-08'}


def test_remove_game_then_rebuild_stays_consistent(games_dir):
    """A rebuild must not resurrect a deleted game -- the file is gone."""
    target = game_archive.list_games(games_dir, HOME)[0]
    game_archive.remove_game(games_dir, target['content_hash'])

    count = game_archive.rebuild_manifest(games_dir)

    assert count == 1
