from flask import Blueprint, request, jsonify, render_template
from flask.typing import ResponseReturnValue
from flask_login import login_required, logout_user, current_user

from app.db.models import db
from app.services.auth import Auth
from app.services.branding_loader import BrandingLoader

account_bp = Blueprint('account', __name__)


@account_bp.route('/account')
@login_required
def account_page() -> ResponseReturnValue:
    """Render the account settings page."""
    branding = BrandingLoader.get_branding(current_user.school_id)
    logo_path = f"/storage/schools/{current_user.school_id}/assets/logo.png"
    return render_template('account.html', branding=branding, logo_path=logo_path)


# ── Password ─────────────────────────────────────────────────────────────────

@account_bp.route('/api/account/password', methods=['POST'])
@login_required
def update_password() -> ResponseReturnValue:
    """Change the current user's password after verifying the current one."""
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return jsonify({'error': 'Please fill in all fields.'}), 400
    if len(new_password) < 8:
        return jsonify({'error': 'New password must be at least 8 characters.'}), 400
    if not Auth.verify_password(current_user, current_password):
        return jsonify({'error': 'Current password is incorrect.'}), 400

    try:
        Auth.update_password(current_user, current_password, new_password)
        return jsonify({'message': 'Password updated successfully.'}), 200
    except Exception:
        return jsonify({'error': 'Failed to update password.'}), 500


# ── Personal information ──────────────────────────────────────────────────────

@account_bp.route('/api/account/information', methods=['POST'])
@login_required
def update_information() -> ResponseReturnValue:
    """Update the current user's name and/or email."""
    data = request.get_json()
    name = data.get('name', '')
    first_name = name.split(' ')[0] if name else current_user.first_name
    last_name = name.split(' ')[1] if name and ' ' in name else current_user.last_name
    email = data.get('email')

    if not first_name or not last_name or not email:
        return jsonify({'error': 'Please fill in all fields.'}), 400

    try:
        # Only call update methods when values actually changed
        if email != current_user.email:
            Auth.update_email(current_user, email)
        if first_name != current_user.first_name or last_name != current_user.last_name:
            Auth.update_name(current_user, first_name, last_name)
        return jsonify({'message': 'Information updated successfully.'}), 200
    except Exception:
        return jsonify({'error': 'Failed to update information.'}), 500


# ── Report display preferences ──────────────────────────────────────────────

CHART_STYLES = {'auto', 'pitch_point'}
INK_MODES = {'full_color', 'light_ink'}


@account_bp.route('/api/account/preferences', methods=['POST'])
@login_required
def update_preferences() -> ResponseReturnValue:
    """Update the current user's report display preferences. Each preference is
    independent -- a request only needs to include the one(s) it's changing."""
    data = request.get_json()

    if 'chart_style' in data:
        if data['chart_style'] not in CHART_STYLES:
            return jsonify({'error': 'Invalid chart style.'}), 400
        current_user.chart_style = data['chart_style']

    if 'ink_mode' in data:
        if data['ink_mode'] not in INK_MODES:
            return jsonify({'error': 'Invalid ink mode.'}), 400
        current_user.ink_mode = data['ink_mode']

    try:
        db.session.commit()
        return jsonify({'message': 'Preferences updated successfully.'}), 200
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to update preferences.'}), 500


# ── Account deletion ──────────────────────────────────────────────────────────

@account_bp.route('/api/account/delete', methods=['POST'])
@login_required
def delete_account() -> ResponseReturnValue:
    """Delete the current user's account (blocked for the school's admin)."""
    data = request.get_json()
    if data.get('confirm') != 'DELETE':
        return jsonify({'error': 'Please type DELETE to confirm account deletion.'}), 400

    # Prevent deleting the admin account — the school record depends on it
    if current_user.email == current_user.school.admin_email:
        return jsonify({'error': 'The administrator account cannot be deleted. Please cancel subscription or change administrator if you wish to delete your school and all associated accounts.'}), 400

    try:
        # Cache the ID before session is cleared by logout_user()
        user_id = current_user.id
        logout_user()
        user = db.session.get(type(current_user), user_id)
        db.session.delete(user)
        db.session.commit()
        return jsonify({'message': 'Account deleted successfully.'}), 200
    except Exception:
        return jsonify({'error': 'Failed to delete account.'}), 500
