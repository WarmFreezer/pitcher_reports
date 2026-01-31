'''
Copyright (c) 2026 Thomas Eubank
Licensed for non-commercial use only. See LICENSE file.

Author:
Thomas Eubank
606-303-4052
thomas.eubank516@gmail.com

Purpose: Generates pitcher performance reports from game datasets exported from TrackMan.
'''

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import pandas as pd
import os
import magic
from werkzeug.utils import secure_filename
import app.services.report as report
import app.services.pdf_generator as pdf_generator
import app.services.file_validator as file_validator

app = Flask(__name__,
            template_folder='app/templates',
            static_folder='app/static')
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
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Delete old input files
    import glob
    old_excels = glob.glob('app/input/*.xlsx ') + glob.glob('app/input/*.xls') + glob.glob('app/input/*.csv')
    for old_excel in old_excels:
        try:
            os.remove(old_excel)
        except Exception as e:
            pass

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
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
        old_images = glob.glob('app/static/output/*.png')
        for old_image in old_images:
            try:
                os.remove(old_image)
            except Exception as e:
                pass

        # Delete old pdfs
        old_pdfs = glob.glob('app/static/pdfs/*.pdf')
        for old_pdf in old_pdfs:
            try:
                os.remove(old_pdf)
            except Exception as e:
                pass

        # Create list of report data
        reports = []
        for pitcher_id in df['PitcherId'].unique():
            # Generate heat map
            report.pitch_heat_map_by_batter_side(filepath, pitcher_id, 0.75)
            
            # Build table data
            table_data = report.build_table(filepath, pitcher_id)
            report_html = table_data[1].to_html(index=False, float_format='%.2f', border=0, classes='pitcher-data-table', escape=False, justify='left', na_rep='')

            # Add to reports list
            reports.append({
                'pitcher_name': table_data[0],
                'pitcher_id': str(pitcher_id),
                'pitcher_table': report_html,
                'image_url': f'/static/output/pitcher_{pitcher_id}_heat_map.png',
                'pdf_url': f'/static/pdfs/pitcher_{pitcher_id}_report.pdf'
            })

            # Generate PDF report
            pdf_file = pdf_generator.create_pitcher_pdf_from_html(
                pitcher_name=table_data[0],
                pitcher_id=pitcher_id,
                table_html=report_html,
                image_path=f'app/static/output/pitcher_{pitcher_id}_heat_map.png',
                output_path=f'app/static/pdfs/pitcher_{pitcher_id}_report.pdf'
            )

        # Merge all PDFs into one
        merged_pdf_path = 'app/static/pdfs/merged_pitcher_reports.pdf'
        pdf_generator.merge_pdfs(app.config['PDF_FOLDER'], merged_pdf_path)

        return jsonify({
            'message': 'File processed successfully',
            'num_reports': len(reports),
            'reports': reports,
            'merged_pdf_url': '/static/pdfs/merged_pitcher_reports.pdf'
        })
    
    except Exception as e:
        print(f"\n!!! ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    app.run(debug=True)