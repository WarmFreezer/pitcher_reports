"""
Measure the memory cost of the report pipeline on a synthetic season, so a change can be
compared before and after (run it on the old and new code and diff the output).

    python scripts/measure_memory.py [--games 40] [--rows 350] [--cols 170] [--pitchers 25]

Peak is tracemalloc's (Python + numpy/pandas allocations), which is portable and
deterministic; it is not process RSS, so treat it as a relative measure. Files are
generated like TrackMan exports: a few dozen columns the reports read, padded with wide
numeric columns to --cols, with repeated string values (teams, names, pitch types).
"""
import argparse
import gc
import json
import os
import sys
import tempfile
import tracemalloc

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import game_archive  # noqa: E402
from app.services.pitch_filters import PitchFilters  # noqa: E402

PITCH_TYPES = ['Fastball', 'Slider', 'Curveball', 'ChangeUp', 'Cutter', 'Sinker']
CALLS = ['BallCalled', 'StrikeCalled', 'StrikeSwinging', 'FoulBallNotFieldable', 'InPlay']


def make_game(rng: np.random.Generator, rows: int, cols: int, day: int, n_pitchers: int) -> pd.DataFrame:
    pitcher = rng.integers(0, n_pitchers, rows)
    frame = pd.DataFrame({
        'Date': f'2026-03-{day % 28 + 1:02d}',
        'HomeTeam': 'HOME_TEAM', 'AwayTeam': 'AWAY_TEAM',
        'PitcherId': 1000 + pitcher, 'Pitcher': [f'Pitcher, Name{p}' for p in pitcher],
        'PitcherTeam': np.where(pitcher % 2 == 0, 'HOME_TEAM', 'AWAY_TEAM'),
        'PitcherThrows': np.where(pitcher % 3 == 0, 'Left', 'Right'),
        'BatterId': 5000 + rng.integers(0, 12, rows), 'Batter': 'Batter, Name',
        'BatterTeam': 'AWAY_TEAM', 'BatterSide': np.where(rng.random(rows) > 0.5, 'Left', 'Right'),
        'TaggedPitchType': rng.choice(PITCH_TYPES, rows), 'PitchCall': rng.choice(CALLS, rows),
        'RelSpeed': rng.normal(88, 5, rows), 'PlateLocSide': rng.normal(0, 0.8, rows),
        'PlateLocHeight': rng.normal(2.4, 0.9, rows),
        'Balls': rng.integers(0, 4, rows), 'Strikes': rng.integers(0, 3, rows),
    })
    extra = {f'Metric{i}': rng.normal(size=rows) for i in range(cols - len(frame.columns))}
    return pd.concat([frame, pd.DataFrame(extra)], axis=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--games', type=int, default=40)
    ap.add_argument('--rows', type=int, default=350)
    ap.add_argument('--cols', type=int, default=170)
    ap.add_argument('--pitchers', type=int, default=25)
    args = ap.parse_args()
    rng = np.random.default_rng(1)

    with tempfile.TemporaryDirectory() as games_dir:
        entries = []
        for i in range(args.games):
            name = f'game_{i:03d}.csv'
            make_game(rng, args.rows, args.cols, i, args.pitchers).to_csv(os.path.join(games_dir, name), index=False)
            entries.append({'file': name, 'date': f'2026-03-{i % 28 + 1:02d}', 'content_hash': f'h{i:03d}'})
        with open(os.path.join(games_dir, 'index.json'), 'w') as f:
            json.dump(entries, f)

        results: dict[str, float] = {}

        def run(label: str, fn):
            gc.collect()
            tracemalloc.start()
            out = fn()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            results[label] = peak / 1024 / 1024
            return out

        hashes = [e['content_hash'] for e in entries]
        frame = run('load selection (peak MB)', lambda: game_archive.load_games(games_dir, hashes))
        results['frame size (MB)'] = float(frame.memory_usage(deep=True).sum()) / 1024 / 1024

        filters = PitchFilters.from_request({'pitch_types': PITCH_TYPES[:3], 'velo_min': 70, 'velo_max': 100})
        ids = list(frame['PitcherId'].unique())

        def per_pitcher_filter():
            # What the export used to do: a filtered copy of the whole frame for every pitcher.
            for pid in ids:
                _ = filters.apply(frame)
        run('filter per pitcher (peak MB, extra over frame)', per_pitcher_filter)

        def hoisted_filter():
            filtered = filters.apply(frame)
            for pid in ids:
                _ = filtered[filtered['PitcherId'] == pid]
        run('filter once + slice (peak MB, extra over frame)', hoisted_filter)

        del frame
        cached = lambda: [game_archive.load_games_cached(games_dir, hashes) for _ in range(5)]
        run('5 cached loads (peak MB)', cached)
        getattr(game_archive, "clear_frame_cache", lambda: None)()

    print(f'{args.games} games x {args.rows} rows x {args.cols} cols, {args.pitchers} pitchers')
    for label, value in results.items():
        print(f'  {label:<52} {value:8.1f}')


if __name__ == '__main__':
    main()
