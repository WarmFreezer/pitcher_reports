"""
Chart images rendered in the user's browser (Plotly.toImage) and posted back for the PDF.

Everything in a report except these images is recomputed on the server from the user's
own archived games; the image bytes are the one client-supplied input, so they are
validated hard before anything touches ReportLab: a base64 PNG data URL, bounded size
and dimensions, and actually decodable as a PNG.

Pure Python, no Flask -- see app/services/CLAUDE.md.
"""
import base64
import binascii
import io
import os

from PIL import Image, UnidentifiedImageError

PNG_PREFIX = 'data:image/png;base64,'
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_IMAGE_SIDE = 4000


class InvalidChartImage(ValueError):
    pass


def save_chart_image(data_url: object, dest_path: str) -> None:
    """
    Decode and validate one posted PNG data URL, then write it to dest_path.

    Raises InvalidChartImage for anything that isn't a sane PNG. The file is re-encoded
    through Pillow rather than written as received, so what lands on disk is exactly a
    PNG Pillow produced from the decoded pixels.
    """
    if not isinstance(data_url, str) or not data_url.startswith(PNG_PREFIX):
        raise InvalidChartImage('Chart image must be a PNG data URL.')

    encoded = data_url[len(PNG_PREFIX):]
    if len(encoded) > MAX_IMAGE_BYTES * 4 // 3 + 4:
        raise InvalidChartImage('Chart image is too large.')

    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidChartImage('Chart image is not valid base64.')
    if len(raw) > MAX_IMAGE_BYTES:
        raise InvalidChartImage('Chart image is too large.')

    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.format != 'PNG':
                raise InvalidChartImage('Chart image must be a PNG.')
            width, height = img.size
            if not (0 < width <= MAX_IMAGE_SIDE and 0 < height <= MAX_IMAGE_SIDE):
                raise InvalidChartImage('Chart image dimensions are out of range.')
            img.load()
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            img.save(dest_path, format='PNG')
    except InvalidChartImage:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise InvalidChartImage('Chart image could not be decoded.')
