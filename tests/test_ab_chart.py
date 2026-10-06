"""The at-bat panels in the pitch-by-pitch PDFs (native ReportLab drawings) and the shared velocity scale."""
import pytest
from reportlab.graphics.shapes import Circle, String

from app.services import ab_chart
from app.services.pitch_stats import PitchByPitchPitch
from app.services.velo_scale import velo_scale


def _pitch(number, side=0.0, height=2.5, velo=90.0):
    return PitchByPitchPitch(
        number=number, pitch_type='Fastball', velo=velo, balls=0, strikes=0, result='StrikeCalled',
        plate_loc_side=side, plate_loc_height=height)


def _shapes(drawing, kind):
    return [s for s in drawing.contents if isinstance(s, kind)]


# --- velocity scale ----------------------------------------------------------

def test_scale_is_the_quartiles():
    assert velo_scale([80.0, 85.0, 90.0, 95.0, 100.0]) == (85.0, 95.0)


def test_scale_keeps_a_minimum_span_for_a_very_consistent_arm():
    lo, hi = velo_scale([90.0] * 8)

    assert hi - lo == pytest.approx(1.0)


def test_scale_handles_one_pitch_and_none():
    assert velo_scale([92.0]) == (91.5, 92.5)
    assert velo_scale([]) is None


def test_scale_ignores_missing_speeds():
    assert velo_scale([float('nan'), 80.0, 100.0]) == velo_scale([80.0, 100.0])


def test_temperature_runs_cool_to_hot_and_clamps():
    cold, hot = ab_chart.temperature_color(0.0), ab_chart.temperature_color(1.0)

    assert cold.blue > cold.red and hot.red > hot.blue
    assert ab_chart.temperature_color(-5) == cold and ab_chart.temperature_color(5) == hot


# --- the drawing ---------------------------------------------------------------

def test_draws_one_numbered_dot_per_located_pitch():
    drawing = ab_chart.ab_chart_drawing([_pitch(1), _pitch(2, 0.5, 3.0), _pitch(3, -0.4, 1.8)], 180)

    assert len(_shapes(drawing, Circle)) == 3
    labels = [s.text for s in _shapes(drawing, String)]
    assert {'1', '2', '3'} <= set(labels)


def test_the_drawing_is_the_requested_width_with_a_square_plot():
    drawing = ab_chart.ab_chart_drawing([_pitch(1)], 180)

    assert drawing.width == 180
    assert drawing.height < drawing.width    # the width includes the velocity key


def test_no_located_pitch_means_no_chart():
    unlocated = PitchByPitchPitch(
        number=1, pitch_type='Fastball', velo=90.0, balls=0, strikes=0, result='BallCalled')

    assert ab_chart.ab_chart_drawing([unlocated], 180) is None
    assert ab_chart.ab_chart_drawing([], 180) is None


def test_unlocated_pitches_are_skipped_but_the_rest_are_drawn():
    unlocated = PitchByPitchPitch(
        number=2, pitch_type='Slider', velo=80.0, balls=0, strikes=0, result='BallCalled')

    drawing = ab_chart.ab_chart_drawing([_pitch(1), unlocated], 180)

    assert len(_shapes(drawing, Circle)) == 1


def test_a_pitch_far_outside_the_panel_is_pinned_inside_the_frame():
    drawing = ab_chart.ab_chart_drawing([_pitch(1, side=40.0, height=-30.0)], 180)

    circle = _shapes(drawing, Circle)[0]
    side = drawing.height
    assert 0 < circle.cx < side and 0 < circle.cy < side
    assert circle.cx + circle.r <= side + 0.01 and circle.cy - circle.r >= -0.01


def test_a_pitch_with_no_tracked_velo_is_gray_not_dropped():
    drawing = ab_chart.ab_chart_drawing([_pitch(1, velo=None), _pitch(2, 0.3, 2.0, 95.0)], 180)

    circles = _shapes(drawing, Circle)
    assert len(circles) == 2
    assert circles[0].fillColor == ab_chart.NO_VELO


def test_faster_pitches_are_hotter_on_a_shared_scale():
    slow, fast = (_pitch(1, velo=82.0), _pitch(2, 0.3, 2.0, 96.0))
    drawing = ab_chart.ab_chart_drawing([slow, fast], 180, velo_lim=(82.0, 96.0))

    cold_dot, hot_dot = _shapes(drawing, Circle)[:2]
    assert cold_dot.fillColor.blue > cold_dot.fillColor.red
    assert hot_dot.fillColor.red > hot_dot.fillColor.blue


def test_the_key_is_drawn_only_when_there_is_a_scale():
    with_scale = ab_chart.ab_chart_drawing([_pitch(1)], 180)
    without = ab_chart.ab_chart_drawing([_pitch(1, velo=None)], 180)

    assert 'mph' in [s.text for s in _shapes(with_scale, String)]
    assert 'mph' not in [s.text for s in _shapes(without, String)]


def test_the_drawing_renders_to_a_pdf_page(tmp_path):
    from reportlab.graphics import renderPDF
    from reportlab.pdfgen import canvas

    drawing = ab_chart.ab_chart_drawing([_pitch(n, n * 0.2 - 0.6, 1.5 + n * 0.4) for n in range(1, 6)], 190)
    c = canvas.Canvas(str(tmp_path / 'panel.pdf'))
    renderPDF.draw(drawing, c, 50, 500)
    c.save()

    assert (tmp_path / 'panel.pdf').stat().st_size > 500
