from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, logout_user, current_user

from app.db.models import db
from app.services.auth import Auth
from app.services.branding_loader import BrandingLoader

account_bp = Blueprint('account', __name__)


@account_bp.route('/account')
@login_required
def account_page():
    branding = BrandingLoader.get_branding(current_user.school.slug)
    logo_path = f"/storage/schools/{current_user.school.slug}/assets/logo.png"
    return render_template('account.html', branding=branding, logo_path=logo_path)


# ── Password ─────────────────────────────────────────────────────────────────

@account_bp.route('/api/account/password', methods=['POST'])
@login_required
def update_password():
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
def update_information():
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


# ── Account deletion ──────────────────────────────────────────────────────────

@account_bp.route('/api/account/delete', methods=['POST'])
@login_required
def delete_account():
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
