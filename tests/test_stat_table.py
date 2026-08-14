"""
Unit tests for the StatTable/Column value objects that replaced DataFrames
with mixed raw-float/formatted-string columns in report generation.
"""
from dataclasses import dataclass

from app.services.stat_table import Column, ColumnFormat, StatTable


@dataclass(frozen=True)
class _Row:
    name: str
    pct: float | None
    count: int
    raw: float


class _Table(StatTable[_Row]):
    columns = [
        Column('name', 'Name', ColumnFormat.TEXT),
        Column('pct', 'Pct', ColumnFormat.PERCENT),
        Column('count', 'Count', ColumnFormat.INT),
        Column('raw', 'Raw', ColumnFormat.DECIMAL2),
    ]


def test_to_reportlab_rows_formats_each_column_by_its_own_rule():
    table = _Table([_Row(name='Fastball', pct=52.567, count=12, raw=9.0)])

    rows = table.to_reportlab_rows()

    assert rows[0] == ['Name', 'Pct', 'Count', 'Raw']
    assert rows[1] == ['Fastball', '52.6%', '12', '9.00']


def test_to_dict_uses_headers_as_keys():
    table = _Table([_Row(name='Slider', pct=10.0, count=3, raw=2.0)])

    [row] = table.to_dict()

    assert row == {'Name': 'Slider', 'Pct': '10.0%', 'Count': '3', 'Raw': '2.00'}


def test_none_value_renders_as_empty_string():
    table = _Table([_Row(name='Curveball', pct=None, count=1, raw=1.0)])

    rows = table.to_reportlab_rows()

    assert rows[1][1] == ''


def test_to_html_matches_dataframe_to_html_shape():
    table = _Table([_Row(name='Fastball', pct=50.0, count=5, raw=1.0)])

    html = table.to_html(css_class='my-table')

    assert 'class="my-table"' in html or 'my-table' in html
    assert '<table' in html and '50.0%' in html


def test_empty_table_renders_no_html():
    table = _Table([])

    assert table.to_html() == ''
    assert len(table) == 0
    assert not table
