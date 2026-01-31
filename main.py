'''
Copyright (c) 2026 Thomas Eubank
Licensed for non-commercial use only. See LICENSE file.

Author:
Thomas Eubank
606-303-4052
thomas.eubank516@gmail.com

Purpose: Generates pitcher performance reports from game datasets exported from TrackMan.
'''

import os
import uuid
import magic
import shutil
import pandas as pd
from flask_cors import CORS
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template, session

import app.services.report as report
import app.services.pdf_generator as pdf_generator
import app.services.file_validator as file_validator

app = Flask(__name__,
            template_folder='app/templates',
            static_folder='app/static')
app.secret_key = os.getenv('SECRET_KEY')
CORS(app) 

# Config
UPLOAD_FOLDER = 'app/input'
OUTPUT_FOLDER = 'app/static/output'
PDF_FOLDER = 'app/static/pdfs'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PDF_FOLDER'] = PDF_FOLDER        
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)

required_columns = report.required_columns

@app.route("/")
def index():
    return render_template("index.html")

@app.route('/api/upload', methods=['POST'])
def upload_file():
    session_upload_folder, session_output_folder, session_pdf_folder = get_session_dir()

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Delete old input files
    import glob
    old_excels = glob.glob(os.path.join(session_upload_folder, '*.xlsx')) + glob.glob(os.path.join(session_upload_folder, '*.xls')) + glob.glob(os.path.join(session_upload_folder, '*.csv'))
    for old_excel in old_excels:
        try:
            os.remove(old_excel)
        except Exception as e:
            pass

    filename = secure_filename(file.filename)
    filepath = os.path.join(session_upload_folder, filename)
    file.save(filepath)

    is_valid, result, df = file_validator.validate_uploaded_file(
        file=file, 
        filepath=filepath,
        required_columns=list(required_columns.keys()),
        column_types=required_columns
        )
    
    if not is_valid:
        try: 
            os.remove(filepath)
        except:
            pass

        app.logger.warning(f"File validation failed: {filename} - {result}")

        return jsonify({'error': result}), 400
    
    checksum = result
    app.logger.info(f"Valid file uploaded: {filename} - Checksum: {checksum}")

    try:
        # Delete old output images
        old_images = glob.glob(os.path.join(session_output_folder, '*.png'))
        for old_image in old_images:
            try:
                os.remove(old_image)
            except Exception as e:
                pass

        # Delete old pdfs
        old_pdfs = glob.glob(os.path.join(session_pdf_folder, '*.pdf'))
        for old_pdf in old_pdfs:
            try:
                os.remove(old_pdf)
            except Exception as e:
                pass

        # Create list of report data
        reports = []
        for pitcher_id in df['PitcherId'].unique():
            # Generate heat map
            report.pitch_heat_map_by_batter_side(filepath, session_output_folder, pitcher_id, 0.75)
            
            # Build table data
            table_data = report.build_table(filepath, pitcher_id)
            report_html = table_data[1].to_html(index=False, float_format='%.2f', border=0, classes='pitcher-data-table', escape=False, justify='left', na_rep='')

            # Add to reports list
            reports.append({
                'pitcher_name': table_data[0],
                'pitcher_id': str(pitcher_id),
                'pitcher_table': report_html,
                'image_url': os.path.join(session_output_folder.replace('app/', ''), f'pitcher_{pitcher_id}_heat_map.png'),
                'pdf_url': os.path.join(session_pdf_folder.replace('app/', ''), f'pitcher_{pitcher_id}_report.pdf')
            })

            # Generate PDF report
            pdf_file = pdf_generator.create_pitcher_pdf_from_html(
                pitcher_name=table_data[0],
                pitcher_id=pitcher_id,
                table_html=report_html,
                image_path=os.path.join(session_output_folder, f'pitcher_{pitcher_id}_heat_map.png'),
                output_path=os.path.join(session_pdf_folder, f'pitcher_{pitcher_id}_report.pdf')
            )

        # Merge all PDFs into one
        merged_pdf_path = os.path.join(session_pdf_folder, 'merged_pitcher_reports.pdf')
        pdf_generator.merge_pdfs(session_pdf_folder, merged_pdf_path)

        return jsonify({
            'message': 'File processed successfully',
            'num_reports': len(reports),
            'reports': reports,
            'merged_pdf_url': os.path.join(session_pdf_folder.replace('app/', ''), 'merged_pitcher_reports.pdf')
        })
    
    except Exception as e:
        print(f"\n!!! ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 500

def get_session_dir():
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex

    session_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"session_{session['sid']}")
    session_output_dir = os.path.join(app.config['OUTPUT_FOLDER'], f"session_{session['sid']}")
    session_pdf_dir = os.path.join(app.config['PDF_FOLDER'], f"session_{session['sid']}")
    os.makedirs(session_upload_dir, exist_ok=True)
    os.makedirs(session_output_dir, exist_ok=True)
    os.makedirs(session_pdf_dir, exist_ok=True)
    return session_upload_dir, session_output_dir, session_pdf_dir

if __name__ == '__main__':
    app.run(debug=True)