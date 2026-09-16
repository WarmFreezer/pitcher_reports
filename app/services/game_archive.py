'''
Archive of raw TrackMan game files, kept per school so reports can span a date range.

The pitcher pipeline renders everything from a single in-memory upload, which cannot
answer "how has this hitter looked over the last month". Hitting reports need multiple
games, and the batted-ball detail a spray chart depends on (Bearing, Distance, ExitSpeed,
Angle) only exists at the raw-row level -- the DB stores per-outing aggregates only.

So every saved game is copied into <storage>/schools/<slug>/games/ alongside an
index.json manifest. The manifest records the game date, teams and the batters that
appear in it, which lets the hitter picker and date bounds resolve without opening a
single CSV. Files are only read when a report is actually generated.

Deduplication reuses the same content hash the DB path uses, so saving the same file
twice is a no-op in both places.
'''

import os
import json
import shutil
import tempfile
from typing import Any

import pandas as pd

from app.services.team_stats import hash_file

MANIFEST_NAME = 'index.json'

GameEntry = dict[str, Any]


def _build_entry(source: pd.DataFrame, filename: str, content_hash: str, practice: bool = False) -> GameEntry | None:
    """Derive a manifest entry from a TrackMan file on disk."""
    date = _game_date(source)
    if date is None:
        return None

    return {
        'file': filename,
        'date': date,
        'home_team': _mode_or_blank(source, 'HomeTeam'),
        'away_team': _mode_or_blank(source, 'AwayTeam'),
        'content_hash': content_hash,
        'batters': _batters(source),
        'pitchers': _pitchers(source),
        'catchers': _catchers(source),
        'practice': practice
    }

def rebuild_manifest(games_dir: str) -> int:
    """Re-derive the manifest from the files on disk. Returns the entry count."""
    old = {e['file']: e for e in read_manifest(games_dir)}
    entries = []
    content_hash = None

    for filename in sorted(os.listdir(games_dir)):
        with open(os.path.join(games_dir, filename), 'rb') as f:
            content_hash = hash_file(f)

        if not filename.endswith(('.csv', '.xlsx', '.xls')):
            continue
        source = _read_source(os.path.join(games_dir, filename))
        entry = _build_entry(
            source=source, 
            filename=filename, 
            content_hash=content_hash,
            practice=old.get(filename, {}).get('practice', False)
        )

        if entry is not None:
            entries.append(entry)
        else:
            print(f"Could not determine a game date for {filename}; skipping.")
            continue

    entries.sort(key=lambda e: e.get('date', ''))
    _write_manifest(games_dir, entries)
    return len(entries)

def _manifest_path(games_dir: str) -> str:
    return os.path.join(games_dir, MANIFEST_NAME)


def read_manifest(games_dir: str) -> list[GameEntry]:
    """Return the list of archived game entries. Missing or corrupt manifest reads as empty."""
    path = _manifest_path(games_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Could not read game manifest {path}: {e}")
        return []
    return data if isinstance(data, list) else []


def _write_manifest(games_dir: str, entries: list[GameEntry]) -> None:
    """Write the manifest atomically so an interrupted save cannot truncate the index."""
    path = _manifest_path(games_dir)
    fd, tmp_path = tempfile.mkstemp(dir=games_dir, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _read_source(filepath: str) -> pd.DataFrame:
    if filepath.endswith(('.xlsx', '.xls')):
        return pd.read_excel(filepath)
    return pd.read_csv(filepath, low_memory=False)


def _game_date(source: pd.DataFrame) -> str | None:
    """The date the game was played, as YYYY-MM-DD. Mode, since a file is one game."""
    parsed = pd.to_datetime(source['Date'], errors='coerce').dropna()
    if parsed.empty:
        return None
    return parsed.mode().iloc[0].date().isoformat()


def _mode_or_blank(source: pd.DataFrame, column: str) -> str:
    if column not in source.columns:
        return ''
    values = source[column].dropna()
    if values.empty:
        return ''
    return str(values.mode().iloc[0])


def _normalize_id(value: Any) -> str:
    """
    A TrackMan id as a plain digit string, whatever dtype pandas gave the column.

    A single null id anywhere in a file makes pandas read the whole column as
    float64, and dropna() does not convert it back -- so str() would yield
    '1001.0' for that game and '1001' for a clean one. The same player would then
    carry two different manifest ids and split into two rows in the pickers.
    """
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def _batters(source: pd.DataFrame) -> list[GameEntry]:
    """Every distinct batter in the file, both teams -- team filtering happens at query time."""
    needed = {'BatterId', 'Batter', 'BatterTeam', 'PitchCall'}
    if not needed.issubset(source.columns):
        return []

    rows = source[['BatterId', 'Batter', 'BatterTeam']].dropna(subset=['BatterId'])
    if rows.empty:
        return []

    # first() rather than mode() -- a batter's name and team do not vary within a game
    grouped = rows.groupby('BatterId', sort=False).first()
    return [
        {
            'id': _normalize_id(batter_id),
            'name': str(row['Batter']),
            'team': str(row['BatterTeam']),
            'batted_balls': int(((source['BatterId'] == batter_id) & (source['PitchCall'] == 'InPlay')).sum())
        }
        for batter_id, row in grouped.iterrows()
    ]

def _pitchers(source: pd.DataFrame) -> list[GameEntry]:
    """Every distinct pitcher in the file, both teams -- team filtering happens at query time."""
    needed = {'PitcherId', 'Pitcher', 'PitcherTeam'}
    if not needed.issubset(source.columns):
        return []

    rows = source[['PitcherId', 'Pitcher', 'PitcherTeam']].dropna(subset=['PitcherId'])
    if rows.empty:
        return []

    grouped = rows.groupby('PitcherId', sort=False).first()
    return [
        {
            'id': _normalize_id(pitcher_id),
            'name': str(row['Pitcher']),
            'team': str(row['PitcherTeam']),
        }
        for pitcher_id, row in grouped.iterrows()
    ]

def archive_game(games_dir: str, filepath: str, practice: bool = False) -> GameEntry | None:
    """
    Copy a saved TrackMan file into the school's game archive and index it.

    Returns the manifest entry, or None when the game is already archived or the
    file has no usable date. Mirrors the content-hash dedup in team_stats.add_report.
    """
    with open(filepath, 'rb') as f:
        content_hash = hash_file(f)

    entries = read_manifest(games_dir)
    if any(entry.get('content_hash') == content_hash for entry in entries):
        print("Game already archived. No new file added.")
        return None

    source = _read_source(filepath)

    date = _game_date(source)
    if date is None:
        print(f"Could not determine a game date for {filepath}; not archiving.")
        return None

    extension = os.path.splitext(filepath)[1] or '.csv'
    stored_name = f'{date}_{content_hash[:8]}{extension}'
    shutil.copyfile(filepath, os.path.join(games_dir, stored_name))

    entry = _build_entry(
        source=source,
        filename=stored_name,
        content_hash=content_hash,
        practice=practice
    )
    assert entry is not None, 'date was already confirmed present above'

    entries.append(entry)
    entries.sort(key=lambda e: e.get('date', ''))
    _write_manifest(games_dir, entries)

    return entry


def remove_game(games_dir: str, content_hash: str) -> bool:
    """
    Remove a game from the archive by its content hash.

    Returns True if a game was removed, False if no matching game was found.
    """
    entries = read_manifest(games_dir)

    # Filter out the entry with the matching content hash, copy leftover entries to a new list
    new_entries = [entry for entry in entries if entry.get('content_hash') != content_hash]

    if len(new_entries) == len(entries):
        print(f"No game found with content hash {content_hash}.")
        return False

    # Remove the file from disk
    for entry in entries:
        if entry.get('content_hash') == content_hash:
            file_path = os.path.join(games_dir, entry['file'])
            if os.path.exists(file_path):
                os.remove(file_path)
            break

    _write_manifest(games_dir, new_entries)
    print(f"Game with content hash {content_hash} removed from archive.")
    return True


def _catchers(source: pd.DataFrame) -> list[GameEntry]:
    """Every distinct catcher in the file, both teams -- team filtering happens at query time."""
    needed = {'CatcherId', 'Catcher', 'CatcherTeam'}
    if not needed.issubset(source.columns):
        return []

    rows = source[['CatcherId', 'Catcher', 'CatcherTeam']].dropna(subset=['CatcherId'])
    if rows.empty:
        return []

    grouped = rows.groupby('CatcherId', sort=False).first()
    return [
        {
            'id': _normalize_id(catcher_id),
            'name': str(row['Catcher']),
            'team': str(row['CatcherTeam']),
        }
        for catcher_id, row in grouped.iterrows()
    ]


def date_bounds(games_dir: str) -> tuple[str | None, str | None]:
    """(earliest, latest) archived game date as YYYY-MM-DD, or (None, None) when empty."""
    dates = sorted(entry['date'] for entry in read_manifest(games_dir) if entry.get('date'))
    if not dates:
        return None, None
    return dates[0], dates[-1]



def list_hitters(
    games_dir: str,
    trackman_id: str,
    target: str = 'own',
    start_date: str | None = None,
    end_date: str | None = None,
    batted_only: bool = False,
) -> list[GameEntry]:
    """
    Distinct hitters in the archive, filtered by team.

    target 'own' keeps batters whose BatterTeam matches the school's TrackMan id;
    'opponent' keeps everyone else. Each hitter carries the range of dates they
    actually appear in, so the UI can bound the date pickers per player.
    """
    hitters: dict[str, GameEntry] = {}

    for entry in read_manifest(games_dir):
        date = entry.get('date')
        if not date:
            continue
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue

        for batter in entry.get('batters', []):
            is_own = batter.get('team') == trackman_id
            
            if target == 'opponent' and is_own:
                continue
            if target != 'opponent' and not is_own:
                continue

            batter_id = batter['id']
            existing = hitters.get(batter_id)
            if existing is None:
                hitters[batter_id] = {
                    'id': batter_id,
                    'name': batter.get('name', ''),
                    'team': batter.get('team', ''),
                    'first_date': date,
                    'last_date': date,
                    'batted_balls': batter.get('batted_balls', 0),
                    'games': 1,
                }
            else:
                existing['games'] += 1
                existing['batted_balls'] += batter.get('batted_balls', 0)
                if date:
                    if not existing['first_date'] or date < existing['first_date']:
                        existing['first_date'] = date
                    if not existing['last_date'] or date > existing['last_date']:
                        existing['last_date'] = date

    if batted_only:
        hitters = {k: v for k, v in hitters.items() if v['batted_balls'] > 0}

    return sorted(hitters.values(), key=lambda h: h['name'])


def list_catchers(
    games_dir: str,
    trackman_id: str,
    target: str = 'own',
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[GameEntry]:
    """
    Distinct catchers in the archive, filtered by team.

    target 'own' keeps catchers whose CatcherTeam matches the school's TrackMan
    id; 'opponent' keeps everyone else. Mirrors list_hitters, minus the
    batted-balls concept, which doesn't apply to a catcher.
    """
    catchers: dict[str, GameEntry] = {}

    for entry in read_manifest(games_dir):
        date = entry.get('date')
        if not date:
            continue
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue

        for catcher in entry.get('catchers', []):
            is_own = catcher.get('team') == trackman_id

            if target == 'opponent' and is_own:
                continue
            if target != 'opponent' and not is_own:
                continue

            catcher_id = catcher['id']
            existing = catchers.get(catcher_id)
            if existing is None:
                catchers[catcher_id] = {
                    'id': catcher_id,
                    'name': catcher.get('name', ''),
                    'team': catcher.get('team', ''),
                    'first_date': date,
                    'last_date': date,
                    'games': 1,
                }
            else:
                existing['games'] += 1
                if date:
                    if not existing['first_date'] or date < existing['first_date']:
                        existing['first_date'] = date
                    if not existing['last_date'] or date > existing['last_date']:
                        existing['last_date'] = date

    return sorted(catchers.values(), key=lambda c: c['name'])


def load_games(games_dir: str, content_hashes: list[str]) -> pd.DataFrame:
    """
    Concatenate every archived game whose content hash is in content_hashes.

    Returns an empty DataFrame when nothing is in range.
    """
    frames = []

    for entry in read_manifest(games_dir):
        if entry.get('content_hash') not in content_hashes:
            continue

        path = os.path.join(games_dir, entry['file'])
        if not os.path.exists(path):
            print(f"Archived game missing from disk, skipping: {path}")
            continue

        try:
            frame = _read_source(path)
        except Exception as e:
            print(f"Could not read archived game {path}: {e}")
            continue

        # .copy() before assigning, not after: a freshly-read CSV/XLSX frame with many
        # mixed-dtype columns can already be block-fragmented, and adding a column
        # via item-assignment on top of that is what triggers pandas' fragmentation
        # warning. Copying first consolidates it into one block, so the new column
        # is a single clean insert.
        frame = frame.copy()
        frame['GameDate'] = entry.get('date')
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True, sort=False)


def list_games(
    games_dir: str,
    trackman_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    include_practice: bool = True,
) -> list[GameEntry]:
    """
    List every archived game, optionally filtered by date range.

    Returns a list of dicts with keys: file, date, home_team, away_team, practice.
    """
    games = []
    for entry in read_manifest(games_dir):
        if entry.get('practice') and not include_practice:
            continue

        date = entry.get('date')
        if not date:
            continue
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue

        home_team = entry.get('home_team', '')
        away_team = entry.get('away_team', '')

        if not home_team == trackman_id:
            is_home = False
        else:
            is_home = True
        
        opponent = away_team if is_home else home_team

        label = "vs. " + opponent if is_home else "at " + opponent

        games.append({
            'file': entry.get('file', ''),
            'content_hash': entry.get('content_hash', ''),
            'date': date,
            'label': label,
            'opponent': opponent,
            'practice': entry.get('practice', False),
            'pitcher_count': len(entry.get('pitchers', [])),
            'batter_count': len(entry.get('batters', [])),
        })
    return sorted(games, key=lambda g: g['date'])


def load_range(games_dir: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Concatenate every archived game whose date falls within [start_date, end_date].

    Dates are ISO strings, so lexicographic comparison is chronological. Adds a
    GameDate column taken from the manifest rather than the row's own Date field --
    the manifest is the single authority, and it survives per-file format drift.

    Returns an empty DataFrame when nothing is in range.
    """
    frames = []

    for entry in read_manifest(games_dir):
        date = entry.get('date')
        if not date or date < start_date or date > end_date:
            continue

        path = os.path.join(games_dir, entry['file'])
        if not os.path.exists(path):
            print(f"Archived game missing from disk, skipping: {path}")
            continue

        try:
            frame = _read_source(path)
        except Exception as e:
            print(f"Could not read archived game {path}: {e}")
            continue

        # See load_games' identical .copy()-before-assign for why: a freshly-read
        # frame can already be block-fragmented, and this avoids the pandas
        # PerformanceWarning that item-assignment on top of that triggers.
        frame = frame.copy()
        frame['GameDate'] = date
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True, sort=False)
