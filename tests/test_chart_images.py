"""Validation of the browser-rendered chart PNGs the PDF export accepts."""
import base64
import io

import pytest
from PIL import Image

from app.services import chart_images
from app.services.chart_images import InvalidChartImage, save_chart_image


def _data_url(img_format='PNG', size=(8, 8), prefix=chart_images.PNG_PREFIX):
    buf = io.BytesIO()
    Image.new('RGB', size, 'white').save(buf, format=img_format)
    return prefix + base64.b64encode(buf.getvalue()).decode()


def test_saves_a_valid_png(tmp_path):
    dest = tmp_path / 'nested' / 'chart.png'

    save_chart_image(_data_url(), str(dest))

    with Image.open(dest) as img:
        assert img.format == 'PNG' and img.size == (8, 8)


@pytest.mark.parametrize('bad', [
    None, 123, '', 'not a data url',
    'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=',
    'data:image/png;base64,@@@not-base64@@@',
    'data:image/png;base64,AAAA',   # valid base64, not an image
])
def test_rejects_things_that_are_not_pngs(tmp_path, bad):
    with pytest.raises(InvalidChartImage):
        save_chart_image(bad, str(tmp_path / 'x.png'))

    assert not (tmp_path / 'x.png').exists()


def test_rejects_a_jpeg_labelled_as_png(tmp_path):
    with pytest.raises(InvalidChartImage):
        save_chart_image(_data_url('JPEG'), str(tmp_path / 'x.png'))


def test_rejects_oversized_dimensions(tmp_path):
    with pytest.raises(InvalidChartImage):
        save_chart_image(_data_url(size=(chart_images.MAX_IMAGE_SIDE + 1, 10)), str(tmp_path / 'x.png'))


def test_rejects_an_oversized_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_images, 'MAX_IMAGE_BYTES', 50)

    with pytest.raises(InvalidChartImage):
        save_chart_image(_data_url(size=(64, 64)), str(tmp_path / 'x.png'))
