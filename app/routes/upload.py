import gc
import os
import glob
import pandas as pd
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.services import report, report_lab_generator, file_validator
from app.services.branding_loader import BrandingLoader
from app.services.report_lab_generator import PDF_Generator, merge_pdfs
from app.routes.utils import get_school_directories

upload_bp = Blueprint('upload_api', __name__)

required_columns = report.required_columns


@upload_bp.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    school_temp_folder, school_output_folder = get_school_directories()

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Clean up previous uploads from this user to avoid stale data
    for pattern in [f'{current_user.id}_*.xlsx', f'{current_user.id}_*.xls', f'{current_user.id}_*.csv']:
        for old_file in glob.glob(os.path.join(school_temp_folder, pattern)):
            try:
                os.remove(old_file)
            except Exception as e:
                print(f"Error deleting old file: {old_file} - {e}")

    filename = secure_filename(file.filename)
    filepath = os.path.join(school_temp_folder, f'{current_user.id}_{filename}')
    file.save(filepath)

    if filepath.endswith('.csv'):
        source_df = pd.read_csv(filepath)
    elif filepath.endswith(('.xlsx', '.xls')):
        source_df = pd.read_excel(filepath)
    else:
        raise ValueError("Unsupported file format. Please provide a .csv, .xlsx, or .xls file.")

    # Full validation: extension, MIME type, file signature, column presence, and type checks
    is_valid, result = file_validator.validate_uploaded_file(
        source_df=source_df, file=file, filepath=filepath,
        required_columns=list(required_columns.keys()),
        column_types=required_columns
    )

    if not is_valid:
        try:
            os.remove(filepath)
        except Exception:
            pass
        current_app.logger.warning(f"File validation failed: {filename} - {result}")
        return jsonify({'error': result}), 400

    current_app.logger.info(f"Valid file uploaded: {filename} - Checksum: {result}")

    try:
        # Remove stale images and PDFs from the previous session before generating new ones
        for old_image in glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_*.png')):
            try:
                os.remove(old_image)
            except Exception as e:
                print(f"Error deleting old image: {old_image} - {e}")

        for old_pdf in glob.glob(os.path.join(school_output_folder, f'{current_user.id}_*.pdf')):
            try:
                os.remove(old_pdf)
            except Exception:
                pass

        branding = BrandingLoader.get_branding(current_user.school.slug)

        roster_path = os.path.join(current_app.config['STORAGE'], 'schools', current_user.school.slug, 'assets', 'roster.csv')
        roster = pd.read_csv(roster_path) if os.path.exists(roster_path) else pd.DataFrame()

        gen = PDF_Generator(current_user=current_user, branding=branding)

        target = request.form.get('target', 'own')

        if target == 'opponent':
            matching = source_df[source_df['PitcherTeam'] != current_user.school.trackman_id]
        else:
            matching = source_df[source_df['PitcherTeam'] == current_user.school.trackman_id]

        if matching.empty:
            if target == 'opponent':
                return jsonify({'error': 'No opponent pitching data found in this file. Make sure you uploaded the correct game file.'}), 400
            else:
                return jsonify({'error': f'No pitching data found for your team (TrackMan ID: {current_user.school.trackman_id}). Make sure you uploaded the correct game file.'}), 400

        reports = []
        for pitcher_id in source_df['PitcherId'].unique():
            pitcher_team = source_df.loc[source_df['PitcherId'] == pitcher_id, 'PitcherTeam'].iloc[0]
            is_own = pitcher_team == current_user.school.trackman_id
            if target == 'opponent' and is_own:
                continue
            if target != 'opponent' and not is_own:
                continue

            arm_angle = None
            if current_user.school.is_active:
                for theme in ('light', 'dark'):
                    report.pitch_heat_map_by_batter_side(source_df, current_user.id, school_temp_folder, pitcher_id, 0.75, theme=theme)
                    result = report.pitch_break_map(source_df, current_user.id, school_temp_folder, pitcher_id, 0.75, theme=theme)
                    if arm_angle is None and result is not None:
                        arm_angle = result

            # Auto-add pitchers found in the game file but missing from the roster
            if not roster.empty and pitcher_id not in roster['Trackman ID'].values:
                last_name, first_name = source_df.loc[source_df['PitcherId'] == pitcher_id, 'Pitcher'].iloc[0].split(', ', 1)
                roster = pd.concat([roster, pd.DataFrame([{'Trackman ID': pitcher_id, 'First Name': first_name, 'Last Name': last_name}])], ignore_index=True)

            # Build pitch stat tables for both the web view and the PDF
            table_data = report.build_table(source_df, pitcher_id)
            if not table_data or len(table_data) < 2 or table_data[1] is None:
                raise ValueError(f'Failed to build table data for pitcher ID {pitcher_id}')
            report_html = table_data[4].to_html(index=False, float_format='%.2f', border=0, classes='pitcher-data-table', escape=False, justify='left', na_rep='')

            pitch_usage_data = report.usage_table(source_df, pitcher_id)
            if not pitch_usage_data or len(pitch_usage_data) < 2 or pitch_usage_data[1] is None:
                raise ValueError(f'Failed to build pitch usage table data for pitcher ID {pitcher_id}')
            left_usage_html = pitch_usage_data[0].to_html(index=False, float_format='%.2f', border=0, classes='pitch-usage-table', escape=False, justify='left', na_rep='')
            right_usage_html = pitch_usage_data[1].to_html(index=False, float_format='%.2f', border=0, classes='pitch-usage-table', escape=False, justify='left', na_rep='')

            parts = table_data[0].split('-')
            date = f"{parts[1]}/{parts[2]}/{parts[0]}"
            away_team = table_data[2]
            home_team = table_data[1]

            reports.append({
                'pitcher_id': str(pitcher_id),
                'pitcher_name': table_data[3],
                'pitcher_table': report_html,
                'left_usage_table': left_usage_html,
                'right_usage_table': right_usage_html,
                'heatmap_left_url': f'/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_heat_map_left_light.png',
                'heatmap_right_url': f'/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_heat_map_right_light.png',
                'heatmap_left_dark_url': f'/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_heat_map_left_dark.png',
                'heatmap_right_dark_url': f'/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_heat_map_right_dark.png',
                'breakmap_url': f'/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_break_map_light.png',
                'breakmap_dark_url': f'/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_break_map_dark.png',
                'arm_angle': f'{arm_angle:.1f}°' if arm_angle is not None else '',
                'pdf_url': f'/storage/schools/{current_user.school.slug}/reports/{current_user.id}_pitcher_{pitcher_id}_report.pdf'
            })

            gen.generate_pitcher_report({
                'pitcher_name': table_data[3],
                'pitcher_id': str(pitcher_id),
                'date': date,
                'home_team': home_team,
                'away_team': away_team,
                'pitch_stats': table_data[4],
                'pitch_usage_left': pitch_usage_data[0],
                'pitch_usage_right': pitch_usage_data[1],
                'pitch_heat_map_left': os.path.join(school_temp_folder, f'{current_user.id}_pitcher_{pitcher_id}_heat_map_left_light.png'),
                'pitch_heat_map_right': os.path.join(school_temp_folder, f'{current_user.id}_pitcher_{pitcher_id}_heat_map_right_light.png'),
                'pitch_break_map': os.path.join(school_temp_folder, f'{current_user.id}_pitcher_{pitcher_id}_break_map_light.png'),
            }, os.path.abspath(os.path.join(school_output_folder, f'{current_user.id}_pitcher_{pitcher_id}_report.pdf')))

            # Release per-pitcher data before the next iteration to keep memory usage flat
            del table_data, report_html
            gc.collect()

        # Persist any new roster entries discovered during this upload
        if not roster.empty:
            roster.to_csv(roster_path, index=False)

        merged_pdf_path = os.path.join(school_output_folder, f'{current_user.id}_merged_pitcher_reports.pdf')
        merge_pdfs(current_user.id, school_output_folder, merged_pdf_path)

        return jsonify({
            'message': 'File processed successfully',
            'num_reports': len(reports),
            'reports': reports,
            'merged_pdf_url': f'/storage/schools/{current_user.school.slug}/reports/{current_user.id}_merged_pitcher_reports.pdf',
            'game_data': {'date': date, 'home_team': home_team, 'away_team': away_team},
            'user': {'name': f"{current_user.first_name} {current_user.last_name}", 'school': current_user.school.name}
        })

    except Exception as e:
        print(f"\n!!! ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 500
