'''
Copyright (c) 2026 Thomas Eubank
Licensed for non-commercial use only. See LICENSE file.

author:
Thomas Eubank
606-303-4052
thomas.eubank516@gmail.com

Purpose: Generates pitcher performance reports from game datasets exported from TrackMan.
'''

import os
import glob
import pandas as pd
from flask_cors import CORS
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, send_from_directory

from app.services import report, auth, pdf_generator, file_validator, branding_loader
from app.db import models

STORAGE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storage')

Auth = auth.Auth
db = models.db
User = models.User
School = models.School
Branding_Loader = branding_loader.BrandingLoader
bcrypt = auth.bcrypt

app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
app.secret_key = os.environ.get('APP_SECRET_KEY')
CORS(app) 

# Flask CLI
from app import cli as cli_commands
cli_commands.register_cli_commands(app)

# Database URL Formatting Fix
database_url = os.environ.get('DATABASE_URL', 'sqlite:///pitcher_reports.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

# Config
app.config['SECRET_KEY'] = app.secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['STORAGE'] = STORAGE_FOLDER

os.makedirs(STORAGE_FOLDER, exist_ok=True)

db.init_app(app)

# Initialize Extensions
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Set Global Variables
required_columns = report.required_columns

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Context processor to inject branding into templates
@app.context_processor
def inject_branding():
    if current_user.is_authenticated:
        branding = Branding_Loader.get_branding(current_user.school.slug)
        logo_path = Branding_Loader.get_logo_path(current_user.school.slug)
        return {'branding': branding, 'logo_path': logo_path}
    return {}

# Serve static files
@app.route('/storage/schools/<school_slug>/assets/<path:filename>')
def school_files(school_slug, filename):
    return send_from_directory(os.path.join(app.config['STORAGE'], 'schools', school_slug, 'assets'), filename)

# Serve temp files
@app.route('/storage/schools/<school_slug>/temp/<path:filename>')
@login_required
def school_temp_files(school_slug, filename):
    return send_from_directory(os.path.join(app.config['STORAGE'], 'schools', school_slug, 'temp'), filename)

# Serve report files
@app.route('/storage/schools/<school_slug>/reports/<path:filename>')
@login_required
def school_report_files(school_slug, filename):
    return send_from_directory(os.path.join(app.config['STORAGE'], 'schools', school_slug, 'reports'), filename)

@app.route('/login', methods=['GET', 'POST'])
def login(): 
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = Auth.get_user_by_email(email)

        if user and Auth.verify_password(user, password):
            login_user(user, remember=request.form.get('remember'))
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route("/upload")
@login_required
def upload():
    return render_template('index.html')

@app.route("/about")
def about():
    return render_template('about.html')

# ****** API Endpoints ******
@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    school_temp_folder, school_output_folder = get_school_directories()

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Delete old input files
    old_excels = glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_*.xlsx')) + \
                 glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_*.xls')) + \
                 glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_*.csv'))
    for old_excel in old_excels:
        try:
            os.remove(old_excel)
        except Exception as e:
            print (f"Error deleting old file: {old_excel} - {e}")
            pass

    filename = secure_filename(file.filename)
    filepath = os.path.join(school_temp_folder, f'{current_user.id}_{filename}')
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
        old_images = glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_*.png'))
        for old_image in old_images:
            try:
                os.remove(old_image)
            except Exception as e:
                print(f"Error deleting old image: {old_image} - {e}")
                pass
        
        # Delete old pdfs
        old_pdfs = glob.glob(os.path.join(school_output_folder, f'{current_user.id}_*.pdf'))
        for old_pdf in old_pdfs:
            try:
                os.remove(old_pdf)
            except Exception as e:
                pass

        # Load Branding data per school
        branding = Branding_Loader.get_branding(current_user.school.slug)

        # Create list of report data
        reports = []
        for pitcher_id in df['PitcherId'].unique():
            # Generate heat map
            report.pitch_heat_map_by_batter_side(current_user.id, filepath, school_temp_folder, pitcher_id, 0.75)
            report.pitch_break_map(current_user.id, filepath, school_temp_folder, pitcher_id, 0.75)

            # Build table data
            table_data = report.build_table(filepath, pitcher_id)
            report_html = table_data[1].to_html(index=False, float_format='%.2f', border=0, classes='pitcher-data-table', escape=False, justify='left', na_rep='')

            # Add to reports list
            reports.append({
                'pitcher_name': table_data[0],
                'pitcher_id': str(pitcher_id),
                'pitcher_table': report_html,
                'heatmap_url': f'/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_heat_map.png',
                'breakmap_url': f'/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_break_map.png',
                'pdf_url': f'/storage/schools/{current_user.school.slug}/reports/{current_user.id}_pitcher_{pitcher_id}_report.pdf'
            })

            # Generate PDF report
            pdf_file = pdf_generator.create_pitcher_pdf_from_html(
                current_user=current_user,
                pitcher_name=table_data[0],
                pitcher_id=pitcher_id,
                table_html=report_html,
                output_path=os.path.abspath(os.path.join(school_output_folder, f'{current_user.id}_pitcher_{pitcher_id}_report.pdf')),
                branding=branding
            )

        # Merge all PDFs into one
        merged_pdf_path = os.path.join(school_output_folder, f'{current_user.id}_merged_pitcher_reports.pdf')
        pdf_generator.merge_pdfs(school_output_folder, merged_pdf_path)

        return jsonify({
            'message': 'File processed successfully',
            'num_reports': len(reports),
            'reports': reports,
            'merged_pdf_url': f'/storage/schools/{current_user.school.slug}/reports/{current_user.id}_merged_pitcher_reports.pdf',
            'user': {
                'name': f"{current_user.first_name} {current_user.last_name}",
                'school': current_user.school.name
            }
        })
    
    except Exception as e:
        print(f"\n!!! ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 500

def get_school_directories():
    if not current_user.is_authenticated:
        raise Exception("User not authenticated")
    
    school_slug = current_user.school.slug

    school_temp_dir = os.path.join(app.config['STORAGE'], 'schools', f'{school_slug}', 'temp')
    school_output_dir = os.path.join(app.config['STORAGE'], 'schools', f'{school_slug}', 'reports')

    # Create directories if they don't exist
    os.makedirs(school_temp_dir, exist_ok=True)
    os.makedirs(school_output_dir, exist_ok=True)

    return school_temp_dir, school_output_dir

if __name__ == '__main__':
    app.run()