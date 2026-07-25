import io

import pandas as pd
import pytest
from werkzeug.datastructures import FileStorage

from app.services import file_validator as fv
from app.services.report import required_columns

VALID_CSV = (
    "Pitcher,PitcherId,TaggedPitchType,PlateLocHeight,PlateLocSide,BatterSide,"
    "RelSpeed,InducedVertBreak,HorzBreak,SpinRate,VertApprAngle,HorzApprAngle,"
    "RelHeight,RelSide,Extension,Tilt,ZoneTime,PitchCall,PitcherTeam,BatterTeam,"
    "Date,Inning,PAofInning,PitchofPA,BatterId,Balls,Strikes\n"
    "\"Doe, John\",1001,Fastball,2.5,0.0,Right,90.0,15.0,-6.0,2200,-5.5,1.2,6.0,-1.8,"
    "6.3,12:30,1,StrikeCalled,HOME,AWAY,2026-01-15,1,1,1,200,0,0\n"
)


def _make_file_storage(content: bytes, filename: str, content_type: str = 'text/csv') -> FileStorage:
    return FileStorage(stream=io.BytesIO(content), filename=filename, content_type=content_type)


def _write(tmp_path, name, content: bytes):
    path = tmp_path / name
    path.write_bytes(content)
    return str(path)


def test_check_extension_rejects_unsupported():
    ok, msg = fv.file_validator.check_extension('report.pdf')
    assert not ok
    assert 'extension' in msg.lower()


def test_check_extension_accepts_csv():
    ok, ext = fv.file_validator.check_extension('report.csv')
    assert ok
    assert ext == 'csv'


@pytest.mark.parametrize('bad_name', ['../secrets.csv', 'a/b.csv', 'a\\b.csv', 'x\x00.csv'])
def test_check_filename_rejects_path_traversal(bad_name):
    ok, msg = fv.file_validator.check_filename(bad_name)
    assert not ok


def test_check_file_size_rejects_empty_file():
    file = _make_file_storage(b'', 'empty.csv')
    ok, msg = fv.file_validator.check_file_size(file)
    assert not ok
    assert 'empty' in msg.lower()


def test_check_file_size_rejects_oversized_file():
    big_content = b'a' * (fv.MAX_FILE_SIZE + 1)
    file = _make_file_storage(big_content, 'big.csv')
    ok, msg = fv.file_validator.check_file_size(file)
    assert not ok
    assert 'too large' in msg.lower()


@pytest.mark.parametrize('signature', [b'#!/bin/sh\necho hi', b'<script>alert(1)</script>', b'MZ\x90\x00'])
def test_check_file_signature_rejects_dangerous_content(tmp_path, signature):
    path = _write(tmp_path, 'evil.csv', signature)
    ok, msg = fv.file_validator.check_file_signature(path)
    assert not ok
    assert 'dangerous' in msg.lower()


def test_validate_content_structure_rejects_empty_dataframe():
    ok, msg = fv.file_validator.validate_content_structure(pd.DataFrame())
    assert not ok
    assert 'no data' in msg.lower()


def test_validate_required_columns_reports_missing():
    df = pd.DataFrame({'Pitcher': ['Doe, John']})
    ok, msg = fv.file_validator.validate_required_columns(df, ['Pitcher', 'PitcherId'])
    assert not ok
    assert 'PitcherId' in msg


def test_check_data_types_rejects_non_numeric_value():
    df = pd.DataFrame({'RelSpeed': ['90.0', 'not-a-number']})
    ok, msg = fv.file_validator.check_data_types(df, {'RelSpeed': 'numeric'})
    assert not ok


def test_check_data_types_accepts_comma_separated_numbers():
    df = pd.DataFrame({'SpinRate': ['2,200', '2,300']})
    ok, msg = fv.file_validator.check_data_types(df, {'SpinRate': 'numeric'})
    assert ok


def test_validate_uploaded_file_end_to_end_valid_csv(tmp_path):
    content = VALID_CSV.encode('utf-8')
    filepath = _write(tmp_path, 'sample.csv', content)
    df = pd.read_csv(filepath)
    file = _make_file_storage(content, 'sample.csv')

    ok, result = fv.validate_uploaded_file(
        source_df=df, file=file, filepath=filepath,
        required_columns=list(required_columns.keys()),
        column_types=required_columns,
    )

    assert ok is True
    assert len(result) == 64  # sha256 hex digest length


def test_validate_uploaded_file_rejects_missing_columns(tmp_path):
    content = b'Pitcher,PitcherId\n"Doe, John",1001\n'
    filepath = _write(tmp_path, 'incomplete.csv', content)
    df = pd.read_csv(filepath)
    file = _make_file_storage(content, 'incomplete.csv')

    ok, result = fv.validate_uploaded_file(
        source_df=df, file=file, filepath=filepath,
        required_columns=list(required_columns.keys()),
        column_types=required_columns,
    )

    assert ok is False
    assert 'missing required columns' in result.lower()
