import os
import magic
import hashlib
import re
import numpy as np
import pandas as pd
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

# Broad MIME set — CSV can be reported as text/plain or application/csv depending on the OS
ALLOWED_MIME_TYPES = {
    'text/csv',
    'text/plain',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/csv',
    'application/x-csv'
}

# Magic bytes that indicate executable or script content — reject these regardless of extension
DANGEROUS_SIGNATURES = {
    b'MZ',          # Windows PE executable
    b'\x7fELF',     # ELF binary (Linux/macOS executable)
    b'#!/',         # Shell script
    b'<?php',       # PHP script
    b'<script',     # HTML/JS injection
    b'javascript:'  # JavaScript URI
}

MAX_FILE_SIZE = 16 * 1024 * 1024
MAX_ROWS = 50000
MAX_COLUMNS = 500


class file_validator:
    @staticmethod
    def _is_valid_timestamp_value(value):
        if pd.isna(value):
            return True

        text = str(value).strip()
        if text.lower() in {'', 'nan', 'none', 'nat'}:
            return True

        # Try each common TrackMan time format before rejecting
        formats = ('%I:%M:%S %p', '%I:%M %p', '%H:%M:%S', '%H:%M')
        for timestamp_format in formats:
            try:
                parsed = pd.to_datetime(text, format=timestamp_format, errors='raise')
                return isinstance(parsed, pd.Timestamp)
            except Exception:
                continue

        return False

    @staticmethod
    def check_extension(filename):
        if '.' not in filename:
            return False, 'Filename has no extension'
        ext = filename.rsplit('.', 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return False, 'Unsupported file extension: {}'.format(ext)
        return True, ext

    @staticmethod
    def check_filename(filename):
        # Reject path traversal patterns and null bytes before the file touches disk
        dangerous_patterns = ['..', '/', '\\', '%00', '\x00']
        for pattern in dangerous_patterns:
            if pattern in filename:
                return False, 'Filename contains invalid pattern: {}'.format(pattern)
        if len(filename) > 255:
            return False, 'Filename is too long'
        return True, None

    @staticmethod
    def check_file_size(file):
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        if size == 0:
            return False, 'File is empty'
        if size > MAX_FILE_SIZE:
            return False, 'File too large. Max Size: {} bytes'.format(MAX_FILE_SIZE)
        return True, None

    @staticmethod
    def check_mime_type(filepath):
        # MIME check runs on the saved file path, not the stream, because libmagic
        # needs a seekable file to read the full header reliably
        try:
            mime = magic.Magic(mime=True)
            detected_mime = mime.from_file(filepath)
            if detected_mime not in ALLOWED_MIME_TYPES:
                return False, 'Invalid MIME type: {}'.format(detected_mime)
            return True, detected_mime
        except Exception as e:
            return False, 'MIME type detection error: {}'.format(str(e))

    @staticmethod
    def check_file_signature(filepath):
        # Read the first 256 bytes and check both the header start and interior
        # because some polyglot files embed dangerous content after a valid header
        try:
            with open(filepath, 'rb') as f:
                header = f.read(256)
            for signature in DANGEROUS_SIGNATURES:
                if header.startswith(signature) or signature in header:
                    return False, 'Dangerous file signature detected'
            return True, None
        except Exception as e:
            return False, 'File signature check error: {}'.format(str(e))

    @staticmethod
    def validate_content_structure(df):
        try:
            if df.empty:
                return False, 'File contains no data'
            if len(df.columns) > MAX_COLUMNS:
                return False, 'File has too many columns: {}. Max allowed is {}'.format(len(df.columns), MAX_COLUMNS)
            if len(df) > MAX_ROWS:
                return False, 'File has too many rows: {}. Max allowed is {}'.format(len(df), MAX_ROWS)
            return True, None
        except pd.errors.ParserError as e:
            return False, 'File is malformed: {}'.format(str(e))
        except Exception as e:
            return False, 'Could not parse file: {}'.format(str(e))

    @staticmethod
    def validate_required_columns(df, required_columns):
        missing = set(required_columns) - set(df.columns)
        if missing:
            return False, 'Missing required columns: {}'.format(', '.join(missing))
        return True, None

    @staticmethod
    def check_data_types(df, column_types):
        try:
            for col, expected_type in column_types.items():
                if col not in df.columns:
                    return False, 'Column not found for type check: {}'.format(col)

                if expected_type == 'numeric':
                    # Strip commas and blanks before coercing — TrackMan exports use comma-separated numbers
                    cleaned = (
                        df[col]
                        .astype(str)
                        .str.replace(',', '', regex=False)
                        .replace({'nan': np.nan, '': np.nan, 'None': np.nan})
                    )
                    pd.to_numeric(cleaned, errors='raise')
                elif expected_type == 'timestamp':
                    for value in df[col]:
                        if not file_validator._is_valid_timestamp_value(value):
                            return False, 'Invalid timestamp value in column {}: {}'.format(col, value)
                elif expected_type == 'string':
                    df[col] = df[col].astype(str)
                else:
                    return False, 'Unsupported data type for column {}: {}'.format(col, expected_type)

            return True, None
        except Exception as e:
            return False, 'Data type validation error: {}'.format(str(e))

    @staticmethod
    def calculate_checksum(filepath):
        # SHA-256 checksum used for logging — not for integrity enforcement
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()


def validate_uploaded_file(source_df, file, filepath, required_columns, column_types):
    """Run the full validation pipeline. Returns (True, checksum) or (False, error_message)."""
    filename = secure_filename(file.filename)

    # Order matters: cheap checks (extension, filename) run before expensive ones (MIME, content)
    is_valid, ext_or_msg = file_validator.check_extension(filename)
    if not is_valid:
        return False, ext_or_msg

    is_valid, msg = file_validator.check_filename(filename)
    if not is_valid:
        return False, msg

    is_valid, msg = file_validator.check_file_size(file)
    if not is_valid:
        return False, msg

    is_valid, msg = file_validator.check_mime_type(filepath)
    if not is_valid:
        return False, msg

    is_valid, msg = file_validator.check_file_signature(filepath)
    if not is_valid:
        return False, msg

    is_valid, msg = file_validator.validate_content_structure(source_df)
    if not is_valid:
        return False, msg

    is_valid, msg = file_validator.validate_required_columns(source_df, required_columns)
    if not is_valid:
        return False, msg

    is_valid, msg = file_validator.check_data_types(source_df, column_types)
    if not is_valid:
        return False, msg

    return True, file_validator.calculate_checksum(filepath)
