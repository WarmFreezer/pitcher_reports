import magic
import pandas as pd
import hashlib
import os
from werkzeug.utils import secure_filename
from flask import request, jsonify
import numpy as np

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
ALLOWED_MIME_TYPES = {
    'text/csv',
    'text/plain',
    'application/vnd.ms-excel',  # .xls
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/csv',
    'application/x-csv'
}
DANGEROUS_SIGNATURES = {
    b'MZ',
    b'\x7fELF',
    b'#!/',
    b'<?php',
    b'<script',
    b'javascript:'
}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16 MB
MAX_ROWS = 50000  # Maximum number of rows allowed in the file
MAX_COLUMNS = 200  # Maximum number of columns allowed in the file

class file_validator:
    @staticmethod
    def check_extension(filename):
        if '.' not in filename:
            return False
        
        ext = filename.rsplit('.', 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return False
        
        print('Extension:', ext)
        return True, ext
    
    @staticmethod
    def check_filename(filename):
        dangerous_patterns = ['..', '/', '\\', '%00', '\x00']
        for pattern in dangerous_patterns:
            if pattern in filename:
                return False
            
        if len(filename) > 255:
            return False
        
        return True, None
    
    @staticmethod
    def check_file_size(file):
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        
        if size == 0:
            return False

        if size > MAX_FILE_SIZE:
            return False, 'File too large. Max Size: {} bytes'.format(MAX_FILE_SIZE)
        
        return True, None
    
    @staticmethod
    def check_mime_type(filepath):
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
    def validate_content_structure(filepath, ext):
        try:
            if ext in ['xlsx', 'xls']:
                df = pd.read_excel(filepath)
            elif ext == 'csv':
                df = pd.read_csv(filepath)
            else:
                return False, 'Unsupported file extension for content validation'
            
            if df.empty:
                return False, 'File contains no data'
            
            if len(df.columns) > MAX_COLUMNS:
                return False, 'File has too many columns: {}. Max allowed is {}'.format(len(df.columns), MAX_COLUMNS)
            
            if len(df) > MAX_ROWS:
                return False, 'File has too many rows: {}. Max allowed is {}'.format(len(df), MAX_ROWS)
            
            return True, df
        
        except pd.errors.ParserError as e:
            return False, 'File is malformed: {}'.format(str(e))
        except Exception as e:
            return False, 'Could not parse file: {}'.format(str(e))
        
    @staticmethod
    def validate_required_columns(df, required_columns):
        file_columns = set(df.columns)
        missing = set(required_columns) - file_columns

        if missing:
            return False, 'Missing required columns: {}'.format(', '.join(missing))
        
        return True, None
    
    @staticmethod
    def check_data_types(df, column_types):
        try: 
            for col in column_types:
                expected_type = column_types[col]
                
                if expected_type == 'numeric':
                    cleaned = (
                        df[col]
                        .astype(str)
                        .str.replace(',', '', regex=False)
                        .replace({'nan': np.nan, '': np.nan, 'None': np.nan})
                    )
                     
                    pd.to_numeric(cleaned, errors='raise')  
                elif expected_type == 'datetime':
                    pd.to_datetime(df[col], errors='raise')
                elif expected_type == 'string':
                    df[col] = df[col].astype(str)
                else:
                    return False, 'Unsupported data type for column {}: {}'.format(col, expected_type)
                
            return True, None
        
        except Exception as e:
            return False, 'Data type validation error: {}'.format(str(e))
        
    @staticmethod
    def calculate_checksum(filepath):
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
def validate_uploaded_file(file, filepath, required_columns, column_types):
    filename = secure_filename(file.filename)
    
    is_valid, ext_or_msg = file_validator.check_extension(filename)
    if not is_valid:
        return False, ext_or_msg, None

    is_valid, msg = file_validator.check_filename(filename)
    if not is_valid:
        return False, msg, None

    is_valid, msg = file_validator.check_file_size(file)
    if not is_valid:
        return False, msg, None

    is_valid, msg = file_validator.check_mime_type(filepath)
    if not is_valid:
        return False, msg, None

    is_valid, msg = file_validator.check_file_signature(filepath)
    if not is_valid:
        return False, msg, None

    is_valid, df_or_msg = file_validator.validate_content_structure(filepath, ext_or_msg)
    if not is_valid:
        return False, df_or_msg, None

    df = df_or_msg
    
    is_valid, msg = file_validator.validate_required_columns(df, required_columns)
    if not is_valid:
        return False, msg, None

    is_valid, msg = file_validator.check_data_types(df, column_types)
    if not is_valid:
        return False, msg, None

    checksum = file_validator.calculate_checksum(filepath)
    
    return True, checksum, df