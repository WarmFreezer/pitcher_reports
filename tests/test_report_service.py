import pandas as pd
import pytest

from app.services import report


def _row(**overrides):
    defaults = {
        'Pitcher': 'Doe, John',
        'PitcherId': 1001,
        'TaggedPitchType': 'Fastball',
        'PlateLocHeight': 2.5,
        'PlateLocSide': 0.0,
        'BatterSide': 'Right',
        'RelSpeed': 90.0,
        'InducedVertBreak': 15.0,
        'HorzBreak': -6.0,
        'SpinRate': 2200,
        'VertApprAngle': -5.5,
        'HorzApprAngle': 1.2,
        'RelHeight': 6.0,
        'RelSide': -1.8,
        'Extension': 6.3,
        'Tilt': '12:30',
        'ZoneTime': 1,
        'PitchCall': 'StrikeCalled',
        'PitcherTeam': 'HOME',
        'BatterTeam': 'AWAY',
        'Date': '2026-01-15',
        'Inning': 1,
        'PAofInning': 1,
        'PitchofPA': 1,
        'BatterId': 200,
        'Balls': 0,
        'Strikes': 0,
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture
def source_df():
    rows = [
        # 4 fastballs: 2 called strikes, 1 swinging strike (whiff+CSW), 1 ball
        _row(PitchCall='StrikeCalled', PlateLocHeight=2.5, PlateLocSide=0.0, ZoneTime=1),
        _row(PitchCall='StrikeCalled', PlateLocHeight=2.5, PlateLocSide=0.0, ZoneTime=1),
        _row(PitchCall='StrikeSwinging', PlateLocHeight=1.0, PlateLocSide=1.5, ZoneTime=0),
        _row(PitchCall='BallCalled', PlateLocHeight=4.0, PlateLocSide=0.0, ZoneTime=0),
    ]
    return pd.DataFrame(rows)


def test_build_table_computes_expected_stats(source_df):
    game_report = report.build_table(source_df, 1001)

    assert game_report.header.pitcher_name == 'Doe, John'
    assert game_report.header.home_team == 'HOME'
    assert game_report.header.away_team == 'AWAY'
    assert len(game_report.stats) == 1

    row = game_report.stats.rows[0]
    assert row.pitch_type == 'FB'
    # 2 called strikes + 1 swinging strike out of 4 pitches = 75% CSW
    assert row.csw_pct == 75.0
    # 1 whiff out of 4 = handled inside CSW; verify Zone% uses ZoneTime mean (2 of 4 = 50%)
    assert row.zone_pct == 50.0

    # Formatting is applied only at render time, not on the raw stat
    formatted = game_report.stats.to_reportlab_rows()
    assert formatted[0] == [c.header for c in game_report.stats.columns]
    assert 'CSW' in formatted[0] and 'Zone' in formatted[0]
    csw_col = formatted[0].index('CSW')
    zone_col = formatted[0].index('Zone')
    assert formatted[1][csw_col] == '75.0%'
    assert formatted[1][zone_col] == '50.0%'


def test_build_table_chase_percent_counts_swings_outside_zone():
    rows = [
        # Outside the zone (high) and batter swung — a chase
        _row(PitchCall='StrikeSwinging', PlateLocHeight=4.0, PlateLocSide=0.0),
        # Outside the zone but batter took it — not a chase
        _row(PitchCall='BallCalled', PlateLocHeight=4.0, PlateLocSide=0.0),
        # Inside the zone and swung — not a chase
        _row(PitchCall='StrikeSwinging', PlateLocHeight=2.5, PlateLocSide=0.0),
    ]
    df = pd.DataFrame(rows)
    game_report = report.build_table(df, 1001)

    row = game_report.stats.rows[0]
    assert row.chase_pct == pytest.approx(33.333, abs=0.01)


def test_usage_table_splits_by_batter_side():
    rows = [
        _row(BatterSide='Left', PitchofPA=1, Balls=0, Strikes=0),
        _row(BatterSide='Left', PitchofPA=2, Balls=1, Strikes=0),
        _row(BatterSide='Right', PitchofPA=1, Balls=0, Strikes=2, PitchCall='StrikeSwinging'),
    ]
    df = pd.DataFrame(rows)
    sides = report.usage_table(df, 1001)

    assert sides.left.rows[0].count == 2
    assert sides.right.rows[0].count == 1
    # The one right-handed pitch was a swinging strike -> 100% whiff for that side
    assert sides.right.rows[0].whiff_pct == 100.0


def test_build_table_returns_none_for_missing_pitcher():
    df = pd.DataFrame([_row()])
    # PitcherId not present in the data — Auth: iloc[0] on an empty slice raises, caught internally
    result = report.build_table(df, 999999)
    assert result is None
