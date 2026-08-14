"""
Typed replacement for DataFrames-with-mixed-types in report generation.

A StatTable pairs an ordered list of dataclass rows with a column spec (which
field backs a column, its header, and how to format it), so a value's
formatting rule is declared once instead of being re-derived by every
consumer via isinstance()/column-name checks against a DataFrame whose
columns were silently rewritten from raw floats to formatted percent strings
after construction.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Generic, TypeVar

import pandas as pd


class ColumnFormat(Enum):
    """How a StatTable column's raw value renders as display text."""
    PERCENT = "percent"    # raw float 0-100 -> "12.3%"
    DECIMAL0 = "decimal0"  # raw float -> "12"
    DECIMAL1 = "decimal1"  # raw float -> "12.3"
    DECIMAL2 = "decimal2"  # raw float -> "12.34"
    INT = "int"            # -> "12"
    TEXT = "text"          # already a string (e.g. a pitch abbreviation, an Axis clock time)


@dataclass(frozen=True)
class Column:
    """One display column: which row field backs it, its header, and how to render it."""
    field: str
    header: str
    format: ColumnFormat = ColumnFormat.DECIMAL2
    none_display: str = ''  # rendered in place of a None value, e.g. '-' for an untracked stat


def _format_value(value: Any, fmt: ColumnFormat, none_display: str = '') -> str:
    """Render one cell's raw value as display text, per its column's format."""
    if value is None:
        return none_display
    if fmt is ColumnFormat.PERCENT:
        return f"{value:.1f}%"
    if fmt is ColumnFormat.DECIMAL0:
        return f"{value:.0f}"
    if fmt is ColumnFormat.DECIMAL1:
        return f"{value:.1f}"
    if fmt is ColumnFormat.DECIMAL2:
        return f"{value:.2f}"
    if fmt is ColumnFormat.INT:
        return str(int(value))
    return str(value)


RowT = TypeVar('RowT')


class StatTable(Generic[RowT]):
    """
    Ordered stat rows plus the column spec needed to render them consistently.

    Replaces a DataFrame where some columns held raw floats and others were
    silently overwritten with formatted percent strings after construction --
    every consumer had to isinstance()/column-name-sniff to know which was
    which. Here the format is declared once, on `columns`, by subclasses.
    """

    columns: ClassVar[list[Column]] = []

    def __init__(self, rows: list[RowT]) -> None:
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self) -> Any:
        return iter(self.rows)

    def __bool__(self) -> bool:
        return bool(self.rows)

    def to_reportlab_rows(self) -> list[list[str]]:
        """Header row + formatted rows, ready for reportlab.platypus.Table."""
        header = [col.header for col in self.columns]
        body = [
            [_format_value(getattr(row, col.field), col.format, col.none_display) for col in self.columns]
            for row in self.rows
        ]
        return [header] + body

    def to_dict(self) -> list[dict[str, str]]:
        """Formatted rows as header -> value dicts, for JSON API responses."""
        return [
            {col.header: _format_value(getattr(row, col.field), col.format, col.none_display) for col in self.columns}
            for row in self.rows
        ]

    def to_html(self, css_class: str = '') -> str:
        """Formatted rows as an HTML table, matching the pre-existing DataFrame.to_html() output shape."""
        if not self.rows:
            return ''
        df = pd.DataFrame(self.to_dict())
        return df.to_html(index=False, border=0, classes=css_class, escape=False, justify='left', na_rep='')
