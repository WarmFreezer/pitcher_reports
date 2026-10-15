"""
Render a pitcher report PDF with invented numbers and invented stat names, for social media.

Uses school 1's branding but reads no game data and writes only the PDF (and chart PNGs) under
the output directory -- nothing under app/storage is touched. Run from the repo root:

    python scripts/make_fake_report.py [out_dir]
"""
import os
import random
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app.services import report_lab_generator
from app.services.branding_loader import BrandingLoader
from app.services.pitch_stats import (
    BreakMapLegendEntry, CustomPitchTypeStat, CustomPitchTypeStatsTable, CustomStat, CustomStatsTable,
    PitcherReportRequest, PitcherStatsTable, PitchTypeStat, PitchUsageStat, PitchUsageTable,
)
from app.services.stat_table import Column, ColumnFormat

SCHOOL_ID = 1
random.seed(7)
np.random.seed(7)

# Same fields and formats as the real tables; only the headers differ.
FAKE_HEADERS = ['Pitch', 'Share', 'Floor', 'Zip', 'Ceil', 'Rise', 'Fade', 'Whirl', 'Dive', 'Glide',
                'Perch', 'Slot', 'Reach', 'Tilt', 'Pocket', 'Bite', 'Fool', 'Smash']


class FakeStatsTable(PitcherStatsTable):
    columns = [Column(c.field, h, c.format) for c, h in zip(PitcherStatsTable.columns, FAKE_HEADERS)]


class FakeUsageTable(PitchUsageTable):
    columns = [Column(c.field, h, c.format) for c, h in zip(
        PitchUsageTable.columns, ['Pitch', 'Volume', 'Sting', 'Opener', 'Edge', 'Squeeze', 'Finisher', 'Swish'])]


PITCHES = [('FB', 48, 91.5), ('SL', 24, 83.0), ('CH', 17, 84.5), ('CB', 11, 78.0)]


def stats_table() -> FakeStatsTable:
    rows = []
    for name, share, velo in PITCHES:
        rows.append(PitchTypeStat(
            pitch_type=name, thrown_pct=share, velo_low=velo - 2.1, velo_avg=velo, velo_high=velo + 2.3,
            ivb=random.uniform(-8, 17), hb=random.uniform(-14, 14), spin=random.uniform(1900, 2600),
            vaa=random.uniform(-6.5, -3.5), haa=random.uniform(-2, 2), rel_height=random.uniform(5.4, 5.9),
            rel_side=random.uniform(-2.2, -1.6), extension=random.uniform(6.0, 6.8), axis='1:30',
            zone_pct=random.uniform(44, 62), chase_pct=random.uniform(22, 38),
            csw_pct=random.uniform(24, 36), damage_pct=random.uniform(3, 14),
        ))
    return FakeStatsTable(rows)


def usage_table() -> FakeUsageTable:
    return FakeUsageTable([
        PitchUsageStat(name, int(share * 1.1), random.uniform(55, 72), random.uniform(15, 60),
                       random.uniform(10, 50), random.uniform(15, 60), random.uniform(10, 45),
                       random.uniform(15, 40))
        for name, share, _ in PITCHES
    ])


def custom_stats() -> CustomStatsTable:
    names = ['Zing Index', 'Mirage Rate', 'Whirlwind', 'Gloom %', 'Flux Score', 'Cinder', 'Orbit Rate',
             'Tempo Grade', 'Spark Count', 'Anvil %', 'Drift', 'Echo Rate', 'Pebble %', 'Hover', 'Lull %', 'Summit']
    return CustomStatsTable([CustomStat(n, f"{random.uniform(8, 78):.1f}%") for n in names])


def custom_pitch_tables() -> list[CustomPitchTypeStatsTable]:
    def table(title: str, names: list[str]) -> CustomPitchTypeStatsTable:
        return CustomPitchTypeStatsTable(
            [CustomPitchTypeStat(p, {n: f"{random.uniform(5, 75):.1f}%" for n in names}) for p, _, _ in PITCHES],
            title=title)
    return [
        table('Pitch Type Mirage Stats', ['Zing', 'Mirage', 'Whirl', 'Gloom', 'Cinder', 'Orbit', 'Anvil', 'Drift']),
        table('Pitch Type Rhythm & Reach', ['Tempo', 'Spark', 'Echo', 'Pebble', 'Hover', 'Lull', 'Summit']),
    ]


def heat_map(path: str, seed: int) -> None:
    rng = np.random.default_rng(seed)
    x, y = rng.normal(0, 0.55, 220), rng.normal(2.5, 0.65, 220)
    fig, ax = plt.subplots(figsize=(3.4, 3.6), dpi=200)
    ax.hexbin(x, y, gridsize=14, cmap='YlOrRd', extent=(-1.8, 1.8, 0.5, 4.5))
    ax.add_patch(plt.Rectangle((-0.83, 1.5), 1.66, 2.0, fill=False, lw=2, ec='black'))
    ax.set_xlim(-1.8, 1.8); ax.set_ylim(0.5, 4.5); ax.set_aspect('equal'); ax.axis('off')
    fig.savefig(path, bbox_inches='tight', transparent=True); plt.close(fig)


def break_map(path: str) -> None:
    colors = {'FB': '#d62728', 'SL': '#1f77b4', 'CH': '#2ca02c', 'CB': '#9467bd'}
    centers = {'FB': (-8, 16), 'SL': (6, 2), 'CH': (-14, 6), 'CB': (10, -10)}
    fig, ax = plt.subplots(figsize=(3.6, 3.6), dpi=200)
    for name, share, _ in PITCHES:
        cx, cy = centers[name]
        ax.scatter(np.random.normal(cx, 2.2, share), np.random.normal(cy, 2.2, share), s=14, c=colors[name], alpha=.8)
    ax.axhline(0, c='grey', lw=.8); ax.axvline(0, c='grey', lw=.8)
    ax.set_xlim(-25, 25); ax.set_ylim(-25, 25); ax.set_aspect('equal')
    ax.set_xlabel('Sway'); ax.set_ylabel('Lift')
    fig.savefig(path, bbox_inches='tight'); plt.close(fig)
    return colors


def main() -> None:
    out_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'fake_report_out')
    os.makedirs(out_dir, exist_ok=True)
    left, right, brk = (os.path.join(out_dir, n) for n in ('heat_left.png', 'heat_right.png', 'break.png'))
    heat_map(left, 1); heat_map(right, 2)
    colors = break_map(brk)

    # School 1's real custom script names real stats; the fake tables below replace it.
    report_lab_generator.load_custom_module = lambda *_: None

    branding = BrandingLoader.get_default_branding()  # school 1 has no branding.json of its own; this skips the DB lookup for its name
    gen = report_lab_generator.PDF_Generator(school_id=SCHOOL_ID, branding=branding)
    out = gen.generate_pitcher_report(PitcherReportRequest(
        pitcher_name='Alex Sample', pitcher_id='0', date='10/14/2026', home_team='Demo U', away_team='Sample State',
        pitcher_height="6'2\"", pitcher_weight='195 lbs', pitcher_age=21,
        pitch_stats=stats_table(), pitch_usage_left=usage_table(), pitch_usage_right=usage_table(),
        pitch_heat_map_left=left, pitch_heat_map_right=right, pitch_break_map=brk,
        pitch_break_map_legend=[BreakMapLegendEntry(n, colors[n], s) for n, s, _ in PITCHES],
        custom_stats=custom_stats(), custom_pitch_type_stats=custom_pitch_tables(),
    ), os.path.join(out_dir, 'fake_pitcher_report.pdf'))
    print(out)


if __name__ == '__main__':
    main()
