import os
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from app.db.models import School, db
from app.services.branding_loader import BrandingLoader
from app.services.custom_report_loader import custom_report_path

master_bp = Blueprint('master', __name__, url_prefix='/master')

CUSTOM_REPORT_MAX_BYTES = 1 * 1024 * 1024
CUSTOM_REPORT_FILENAMES = {
    'pitcher': 'custom_pitcher_report.py',
    'hitter': 'custom_hitter_report.py',
}

P = ParamSpec('P')
R = TypeVar('R')


def master_required(view: Callable[P, R]) -> Callable[P, R | ResponseReturnValue]:
    """Restrict a view to users with role == 'master'; flashes and redirects otherwise."""
    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R | ResponseReturnValue:
        if not current_user.is_authenticated or current_user.role != 'master':
            flash('You do not have permission to access that page.', 'danger')
            return redirect(url_for('pages.dashboard'))
        return view(*args, **kwargs)
    return wrapped


@master_bp.route('/schools')
@login_required
@master_required
def schools_list() -> ResponseReturnValue:
    """List every school — pick one to act as, or upload its custom report scripts."""
    all_schools = School.query.order_by(School.name).all()
    default_branding = BrandingLoader.get_default_branding()
    return render_template('master_schools.html', schools=all_schools, default_branding=default_branding)


@master_bp.route('/default-branding', methods=['POST'])
@login_required
@master_required
def update_default_branding() -> ResponseReturnValue:
    """Update the color tokens in the global default.json, used as a branding fallback for schools without their own branding.json."""
    data = request.get_json()
    colors = data.get('colors', {})

    error = BrandingLoader.validate_colors(colors)
    if error:
        return jsonify({'error': error}), 400

    try:
        BrandingLoader.update_default_colors(colors)
        return jsonify({'message': 'Default branding updated successfully.'}), 200
    except Exception:
        return jsonify({'error': 'Failed to update default branding.'}), 500


@master_bp.route('/schools/<int:school_id>/act', methods=['POST'])
@login_required
@master_required
def act_as_school(school_id: int) -> ResponseReturnValue:
    """Start acting as the given school on the subscription blueprint."""
    if not db.session.get(School, school_id):
        flash('School not found.', 'danger')
        return redirect(url_for('master.schools_list'))
    session['master_school_id'] = school_id
    return redirect(url_for('subscription.subscription_page'))


@master_bp.route('/exit', methods=['POST'])
@login_required
@master_required
def exit_masquerade() -> ResponseReturnValue:
    """Stop acting as another school."""
    session.pop('master_school_id', None)
    return redirect(url_for('master.schools_list'))


@master_bp.route('/schools/<int:school_id>/custom-report', methods=['POST'])
@login_required
@master_required
def upload_custom_report(school_id: int) -> ResponseReturnValue:
    """Upload/replace a school's custom_pitcher_report.py or custom_hitter_report.py.

    The uploaded filename is ignored entirely — the server picks the on-disk name from
    report_type, so the uploader never controls the path. Syntax-checked before saving;
    this is not a sandbox, only master accounts (checked above) may reach this route.
    """
    school = db.session.get(School, school_id)
    if not school:
        flash('School not found.', 'danger')
        return redirect(url_for('master.schools_list'))

    filename = CUSTOM_REPORT_FILENAMES.get(request.form.get('report_type', ''))
    if not filename:
        flash('Invalid report type.', 'danger')
        return redirect(url_for('master.schools_list'))

    file = request.files.get('file')
    if not file or not file.filename:
        flash('No file selected.', 'danger')
        return redirect(url_for('master.schools_list'))
    if not file.filename.lower().endswith('.py'):
        flash('Custom report files must be a .py file.', 'danger')
        return redirect(url_for('master.schools_list'))

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size == 0 or size > CUSTOM_REPORT_MAX_BYTES:
        flash('File is empty or exceeds the 1 MB size limit.', 'danger')
        return redirect(url_for('master.schools_list'))

    source = file.read().decode('utf-8', errors='replace')
    try:
        compile(source, filename, 'exec')
    except SyntaxError as e:
        flash(f'File has a syntax error and was not saved: {e}', 'danger')
        return redirect(url_for('master.schools_list'))

    target_path = custom_report_path(school_id, filename)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(source, encoding='utf-8')

    flash(f'{filename} uploaded for {school.name}.', 'success')
    return redirect(url_for('master.schools_list'))
