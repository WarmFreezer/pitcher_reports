import os
import re
import tempfile
import stripe
import unicodedata
import pandas as pd
from io import BytesIO
from datetime import datetime
from PIL import Image
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app, send_file
from flask_login import login_required, current_user

from app.db.models import db
from app.db import models as db_models
from app.services import file_validator
from app.services.branding_loader import BrandingLoader

subscription_bp = Blueprint('subscription', __name__)

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# Image upload constraints shared across logo and pfp endpoints
LOGO_MAX_BYTES = 10 * 1024 * 1024
LOGO_ALLOWED_EXT = {'png', 'jpg', 'jpeg'}

# Required columns and their expected types for uploaded roster files
ROSTER_REQUIRED_COLUMNS = {
    'Trackman ID': 'string',
    'First Name': 'string',
    'Last Name': 'string',
    'Birthday': 'string',
    'Height': 'string',
    'Weight': 'numeric'
}


# ── Page ─────────────────────────────────────────────────────────────────────

@subscription_bp.route('/subscription')
@login_required
def subscription_page():
    # Only the school's admin email may access this page
    if current_user.email != current_user.school.admin_email:
        flash('You do not have permission to access that page.', 'danger')
        return redirect(url_for('pages.dashboard'))

    branding = BrandingLoader.get_branding(current_user.school.slug)
    logo_path = f"/storage/schools/{current_user.school.slug}/assets/logo.png"

    # Fetch up to 12 most recent invoices from Stripe for the billing history table
    invoices = []
    if current_user.school.stripe_customer_id:
        try:
            result = stripe.Invoice.list(customer=current_user.school.stripe_customer_id, limit=12)
            invoices = [{
                'date': datetime.fromtimestamp(inv.created).strftime('%B %d, %Y'),
                'amount': f"${inv.amount_paid / 100:.2f}",
                'status': inv.status,
                'pdf_url': inv.invoice_pdf
            } for inv in result.data]
        except Exception as e:
            current_app.logger.error(f"Error fetching invoices: {e}")

    return render_template('subscription.html', branding=branding, logo_path=logo_path, invoices=invoices)


# ── Subscription management ───────────────────────────────────────────────────

@subscription_bp.route('/api/subscription/cancel', methods=['POST'])
@login_required
def cancel_subscription():
    # Accounts without a Stripe subscription ID are permanent and cannot be cancelled here
    if not current_user.school.stripe_subscription_id:
        return jsonify({'message': 'This is a permanent subscription and cannot be cancelled.', 'permanent': True}), 200
    if current_user.email != current_user.school.admin_email:
        return jsonify({'error': 'Only the school administrator can cancel the subscription.'}), 403
    try:
        # cancel_at_period_end keeps access active until the billing period expires
        stripe.Subscription.modify(current_user.school.stripe_subscription_id, cancel_at_period_end=True)
        current_user.school.stripe_subscription_status = 'canceled'
        db.session.commit()
        return jsonify({'message': 'Subscription cancelled successfully.'}), 200
    except Exception as e:
        current_app.logger.error(f"Error cancelling subscription: {e}")
        return jsonify({'error': 'Failed to cancel subscription.'}), 500


@subscription_bp.route('/api/subscription/start', methods=['POST'])
@login_required
def start_subscription():
    if current_user.email != current_user.school.admin_email:
        return jsonify({'error': 'Only the school administrator can manage the subscription.'}), 403
    try:
        # If the subscription is still alive but pending cancellation, just undo it
        if current_user.school.stripe_subscription_id:
            sub = stripe.Subscription.retrieve(current_user.school.stripe_subscription_id)
            if sub.status in ('active', 'trialing') and sub.cancel_at_period_end:
                stripe.Subscription.modify(current_user.school.stripe_subscription_id, cancel_at_period_end=False)
                current_user.school.stripe_subscription_status = sub.status
                db.session.commit()
                return jsonify({'reactivated': True, 'message': 'Subscription reactivated successfully.'}), 200

        # Subscription is truly gone — open a new Stripe checkout session
        checkout_session = stripe.checkout.Session.create(
            line_items=[{'price': os.environ.get('STRIPE_PRICE_ID'), 'quantity': 1}],
            mode='subscription',
            ui_mode='embedded',
            return_url=f'{request.host_url}return?session_id={{CHECKOUT_SESSION_ID}}',
            customer=current_user.school.stripe_customer_id or None,
            customer_email=None if current_user.school.stripe_customer_id else current_user.school.admin_email,
            metadata={'school_slug': current_user.school.slug}
        )
        return jsonify({'client_secret': checkout_session.client_secret}), 200
    except Exception as e:
        current_app.logger.error(f"Error starting subscription: {e}")
        return jsonify({'error': 'Failed to start subscription.'}), 500


# ── School settings ───────────────────────────────────────────────────────────

@subscription_bp.route('/api/subscription/settings', methods=['POST'])
@login_required
def update_subscription_settings():
    if current_user.email != current_user.school.admin_email:
        return jsonify({'error': 'Only the admin can update school settings.'}), 403
    data = request.get_json()
    new_email = data.get('admin_email', '').strip()
    if not new_email or '@' not in new_email:
        return jsonify({'error': 'Invalid email address.'}), 400
    try:
        current_user.school.admin_email = new_email
        db.session.commit()
        return jsonify({'message': 'Settings updated successfully.'}), 200
    except Exception as e:
        current_app.logger.error(f"Error updating school settings: {e}")
        return jsonify({'error': 'Failed to update settings.'}), 500


@subscription_bp.route('/api/subscription/rebrand', methods=['POST'])
@login_required
def rebrand_subscription():
    data = request.get_json()
    colors = data.get('colors', {})

    # Validate the four editable tokens are present and are valid hex values
    required = {'primary', 'secondary', 'tertiary', 'accent'}
    if not required.issubset(colors.keys()):
        return jsonify({'error': 'Missing required color tokens.'}), 400
    hex_re = re.compile(r'^#[0-9a-fA-F]{6}$')
    for token, value in colors.items():
        if not hex_re.match(value):
            return jsonify({'error': f'Invalid hex color for {token}: {value}'}), 400

    try:
        branding = BrandingLoader.get_branding(current_user.school.slug)
        branding['colors'].update(colors)
        BrandingLoader.update_branding(current_user.school.slug, branding)
        return jsonify({'message': 'Branding updated successfully.'}), 200
    except Exception as e:
        current_app.logger.error(f"Error updating branding: {e}")
        return jsonify({'error': 'Failed to update branding.'}), 500


# ── Branding PDF preview ─────────────────────────────────────────────────────

@subscription_bp.route('/api/subscription/preview-pdf', methods=['GET'])
@login_required
def preview_branding_pdf():
    from app.services.report_lab_generator import PDF_Generator

    branding = BrandingLoader.get_branding(current_user.school.slug)
    gen = PDF_Generator(current_user, branding)

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        tmp_path = f.name

    try:
        gen.generate_color_preview(tmp_path)
        with open(tmp_path, 'rb') as f:
            pdf_bytes = BytesIO(f.read())
    except Exception as e:
        current_app.logger.error(f"Error generating branding preview: {e}")
        return jsonify({'error': 'Failed to generate preview.'}), 500
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    pdf_bytes.seek(0)
    return send_file(pdf_bytes, mimetype='application/pdf', download_name='branding_preview.pdf')


# ── Logo upload ───────────────────────────────────────────────────────────────

@subscription_bp.route('/api/subscription/logo', methods=['POST'])
@login_required
def upload_logo():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided.'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected.'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in LOGO_ALLOWED_EXT:
        return jsonify({'error': 'File must be a PNG or JPG.'}), 400
    file.seek(0, 2)
    if file.tell() > LOGO_MAX_BYTES:
        return jsonify({'error': 'File too large. Maximum size is 10 MB.'}), 400
    file.seek(0)

    # Pillow validates the file is a real image and normalises it to RGBA PNG
    try:
        img = Image.open(file).convert('RGBA')
    except Exception:
        return jsonify({'error': 'Invalid or corrupt image file.'}), 400

    try:
        assets_dir = os.path.join(current_app.config['STORAGE'], 'schools', current_user.school.slug, 'assets')
        os.makedirs(assets_dir, exist_ok=True)
        img.save(os.path.join(assets_dir, 'logo.png'), 'PNG')
        return jsonify({'message': 'Logo uploaded successfully.', 'logo_url': f'/storage/schools/{current_user.school.slug}/assets/logo.png'}), 200
    except Exception as e:
        current_app.logger.error(f"Error saving logo: {e}")
        return jsonify({'error': 'Failed to save logo.'}), 500


# ── Roster helpers ───────────────────────────────────────────────────────────

def _upsert_roster_rows(rows):
    for row in rows:
        trackman_id = str(row.get('Trackman ID', '')).strip()
        if not trackman_id:
            continue
        first  = str(row.get('First Name', '')).strip()
        last   = str(row.get('Last Name',  '')).strip()
        name   = f'{first} {last}'.strip()
        height = str(row.get('Height', '')).strip() or None
        weight = str(row.get('Weight', '')).strip() or None
        birthdate = None
        bday_str = str(row.get('Birthday', '')).strip()
        if bday_str:
            try:
                birthdate = pd.to_datetime(bday_str).date()
            except Exception:
                pass
        pitcher = db_models.Pitcher.query.filter_by(
            trackman_id=trackman_id, school_id=current_user.school_id
        ).first()
        if pitcher:
            if name:
                pitcher.name = name
            pitcher.birthdate = birthdate
            pitcher.height    = height
            pitcher.weight    = weight
        else:
            db.session.add(db_models.Pitcher(
                school_id=current_user.school_id,
                trackman_id=trackman_id,
                name=name,
                birthdate=birthdate,
                height=height,
                weight=weight,
            ))


# ── Roster ────────────────────────────────────────────────────────────────────

@subscription_bp.route('/api/subscription/roster', methods=['GET'])
@login_required
def get_roster():
    pitchers = db_models.Pitcher.query.filter_by(school_id=current_user.school_id).all()
    roster = []
    for p in pitchers:
        parts = (p.name or '').split(' ', 1)
        roster.append({
            'Trackman ID': p.trackman_id or '',
            'First Name':  parts[0] if parts else '',
            'Last Name':   parts[1] if len(parts) > 1 else '',
            'Birthday':    p.birthdate.isoformat() if p.birthdate else '',
            'Height':      p.height or '',
            'Weight':      p.weight or '',
        })
    columns = ['Trackman ID', 'First Name', 'Last Name', 'Birthday', 'Height', 'Weight']
    return jsonify({'roster': roster, 'columns': columns}), 200


@subscription_bp.route('/api/subscription/roster', methods=['PUT'])
@login_required
def save_roster():
    data = request.get_json()
    rows = data.get('rows', [])
    try:
        _upsert_roster_rows(rows)
        db.session.commit()
        return jsonify({'message': 'Roster saved successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving roster: {e}")
        return jsonify({'error': 'Failed to save roster.'}), 500


@subscription_bp.route('/api/subscription/roster', methods=['POST'])
@login_required
def upload_roster():
    from werkzeug.utils import secure_filename
    from app.routes.utils import get_school_directories

    school_temp_folder, _ = get_school_directories()

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(school_temp_folder, f'{current_user.id}_roster_{filename}')
    file.save(filepath)

    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)[list(ROSTER_REQUIRED_COLUMNS.keys())]
    elif filepath.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(filepath)[list(ROSTER_REQUIRED_COLUMNS.keys())]
    else:
        try:
            os.remove(filepath)
        except Exception:
            pass
        return jsonify({'error': 'Unsupported file format. Please provide a .csv, .xlsx, or .xls file.'}), 400

    is_valid, result = file_validator.validate_uploaded_file(
        source_df=df, file=file, filepath=filepath,
        required_columns=list(ROSTER_REQUIRED_COLUMNS.keys()),
        column_types=ROSTER_REQUIRED_COLUMNS
    )

    if not is_valid:
        try:
            os.remove(filepath)
        except Exception:
            pass
        return jsonify({'error': result}), 400

    try:
        _upsert_roster_rows(df.fillna('').to_dict(orient='records'))
        db.session.commit()
        os.remove(filepath)
        return jsonify({'message': 'Roster uploaded successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving roster to DB: {e}")
        try:
            os.remove(filepath)
        except Exception:
            pass
        return jsonify({'error': 'Failed to save roster.'}), 500


# ── Player profile pictures ───────────────────────────────────────────────────

@subscription_bp.route('/api/subscription/roster/pfp/<player_id>', methods=['POST'])
@login_required
def upload_player_pfp(player_id):
    if not re.match(r'^[\w\-]+$', player_id):
        return jsonify({'error': 'Invalid player ID.'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided.'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected.'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in LOGO_ALLOWED_EXT:
        return jsonify({'error': 'File must be a PNG or JPG.'}), 400
    file.seek(0, 2)
    if file.tell() > LOGO_MAX_BYTES:
        return jsonify({'error': 'File too large. Maximum size is 10 MB.'}), 400
    file.seek(0)

    try:
        img = Image.open(file).convert('RGBA')
    except Exception:
        return jsonify({'error': 'Invalid or corrupt image file.'}), 400

    try:
        player_dir = os.path.join(current_app.config['STORAGE'], 'schools', current_user.school.slug, 'assets', 'players', player_id)
        os.makedirs(player_dir, exist_ok=True)
        img.save(os.path.join(player_dir, 'pfp.png'), 'PNG')
        return jsonify({'message': 'Profile picture uploaded successfully.', 'pfp_url': f'/storage/schools/{current_user.school.slug}/assets/players/{player_id}/pfp.png'}), 200
    except Exception as e:
        current_app.logger.error(f"Error saving player pfp: {e}")
        return jsonify({'error': 'Failed to save profile picture.'}), 500


@subscription_bp.route('/api/subscription/roster/pfp/bulk', methods=['POST'])
@login_required
def upload_player_pfp_bulk():
    def normalize(s):
        # Strip diacritics and non-alpha characters so "Martínez" matches "martinez"
        s = unicodedata.normalize('NFD', str(s).lower())
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        return re.sub(r'[^a-z]', '', s)

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files provided.'}), 400

    pitchers = db_models.Pitcher.query.filter_by(school_id=current_user.school_id).all()
    if not pitchers:
        return jsonify({'error': 'No roster found. Please upload a roster first.'}), 400

    name_to_id = {}
    for p in pitchers:
        parts = (p.name or '').split(' ', 1)
        first = normalize(parts[0] if parts else '')
        last  = normalize(parts[1] if len(parts) > 1 else '')
        player_id = str(p.trackman_id or '').strip()
        if first and last and player_id:
            name_to_id[first + last] = player_id
            name_to_id[last + first] = player_id

    matched, unmatched = [], []
    for file in files:
        if not file.filename:
            continue

        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in LOGO_ALLOWED_EXT:
            unmatched.append(file.filename)
            continue

        # Strip path separators from webkitdirectory uploads (e.g. "HEADSHOTS/6_OwensCarter.jpg")
        basename = file.filename.replace('\\', '/').split('/')[-1]
        stem = normalize(os.path.splitext(basename)[0])
        player_id = name_to_id.get(stem)
        if not player_id:
            unmatched.append(file.filename)
            continue

        file.seek(0, 2)
        too_large = file.tell() > LOGO_MAX_BYTES
        file.seek(0)
        if too_large:
            unmatched.append(file.filename)
            continue

        try:
            img = Image.open(file).convert('RGBA')
            player_dir = os.path.join(current_app.config['STORAGE'], 'schools', current_user.school.slug, 'assets', 'players', player_id)
            os.makedirs(player_dir, exist_ok=True)
            img.save(os.path.join(player_dir, 'pfp.png'), 'PNG')
            matched.append(file.filename)
        except Exception as e:
            print(f"!!! PFP SAVE ERROR {file.filename}: {type(e).__name__}: {e}")
            unmatched.append(file.filename)

    return jsonify({
        'message': f'Matched {len(matched)} of {len(matched) + len(unmatched)} photos.',
        'matched': matched,
        'unmatched': unmatched
    }), 200
