"""Pitch type / velocity filtering: request parsing, the mask itself, and filter-bar metadata."""
import pandas as pd
import pytest

from app.services.pitch_filters import PitchFilters, pitch_type_options, velo_bounds


@pytest.fixture
def pitches():
    return pd.DataFrame({
        'PitcherId': [1, 1, 1, 1, 1],
        'TaggedPitchType': ['Fastball', 'Fastball', 'Slider', 'ChangeUp', 'Slider'],
        'RelSpeed': [95.0, 91.5, 84.0, 85.0, None],
    })


# --- parsing ---------------------------------------------------------------

@pytest.mark.parametrize('raw', [None, {}])
def test_no_filters_means_no_restriction(raw):
    parsed = PitchFilters.from_request(raw)

    assert parsed == PitchFilters()
    assert not parsed.is_active


def test_parses_types_and_velo():
    parsed = PitchFilters.from_request({'pitch_types': ['Slider'], 'velo': [90, 80]})

    assert parsed.pitch_types == ('Slider',)
    assert (parsed.velo_min, parsed.velo_max) == (80.0, 90.0)   # a reversed pair is normalised
    assert parsed.is_active


@pytest.mark.parametrize('raw', [
    'Slider',
    {'pitch_types': 'Slider'},
    {'pitch_types': [1]},
    {'pitch_types': ['x' * 41]},
    {'pitch_types': ['Slider'] * 41},
    {'velo': [80]},
    {'velo': 'fast'},
    {'velo': ['a', 'b']},
    {'velo': [True, False]},
    {'velo': [float('nan'), 90]},
    {'velo': [float('inf'), 90]},
])
def test_rejects_malformed_filters(raw):
    with pytest.raises(ValueError):
        PitchFilters.from_request(raw)


# --- applying --------------------------------------------------------------

def test_inactive_filters_return_the_frame_untouched(pitches):
    assert PitchFilters().apply(pitches) is pitches


def test_pitch_type_filter_keeps_only_those_types(pitches):
    kept = PitchFilters(pitch_types=('Slider', 'ChangeUp')).apply(pitches)

    assert sorted(kept['TaggedPitchType'].unique()) == ['ChangeUp', 'Slider']


def test_unchecking_every_type_matches_nothing(pitches):
    assert PitchFilters(pitch_types=()).apply(pitches).empty


def test_velo_range_is_inclusive_and_drops_untracked_pitches(pitches):
    kept = PitchFilters(velo_min=84.0, velo_max=91.5).apply(pitches)

    assert sorted(kept['RelSpeed']) == [84.0, 85.0, 91.5]   # the NaN-velo slider is gone


def test_filters_combine(pitches):
    kept = PitchFilters(pitch_types=('Slider',), velo_min=80, velo_max=90).apply(pitches)

    assert list(kept['RelSpeed']) == [84.0]


def test_velo_filter_tolerates_text_speeds():
    frame = pd.DataFrame({'TaggedPitchType': ['Fastball', 'Fastball'], 'RelSpeed': ['92.1', 'n/a']})

    kept = PitchFilters(velo_min=90, velo_max=95).apply(frame)

    assert len(kept) == 1


def test_empty_frame_is_returned_as_is():
    empty = pd.DataFrame()

    assert PitchFilters(pitch_types=('Slider',)).apply(empty) is empty


# --- filter bar metadata ----------------------------------------------------

def test_pitch_type_options_are_ordered_with_counts(pitches):
    options = pitch_type_options(pitches)

    assert [o['name'] for o in options] == ['Fastball', 'Slider', 'ChangeUp']
    assert [o['count'] for o in options] == [2, 2, 1]
    assert options[0]['abbreviation'] == 'FB'
    assert options[0]['color'].startswith('#')


def test_pitch_type_options_skip_untyped_and_keep_unknown_types():
    frame = pd.DataFrame({'TaggedPitchType': ['n/a', 'Eephus', 'Eephus']})

    options = pitch_type_options(frame)

    assert [(o['name'], o['count']) for o in options] == [('Eephus', 2)]
    assert options[0]['color'] == '#888888'


def test_velo_bounds_round_outward(pitches):
    assert velo_bounds(pitches) == (84, 95)
    assert velo_bounds(pd.DataFrame({'RelSpeed': [84.2, 91.1]})) == (84, 92)


def test_velo_bounds_without_data():
    assert velo_bounds(pd.DataFrame({'RelSpeed': [None, None]})) is None
