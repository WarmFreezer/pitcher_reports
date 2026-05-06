'''
Copyright (c) 2026 Thomas Eubank
Licensed for non-commercial use only. See LICENSE file.

author:
Thomas Eubank
606-303-4052
thomas.eubank516@gmail.com

Purpose: Generates pitcher performance reports from game datasets exported from TrackMan.
'''

import gc
import os
import glob
import stripe
import pandas as pd
from functools import wraps
from flask_cors import CORS
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, send_from_directory, session

from app.services import report, auth, report_lab_generator, file_validator, branding_loader
from app.db import models
import app.payment_routes as payment_routes            

STORAGE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storage')

Auth = auth.Auth
db = models.db
User = models.User
School = models.School
Branding_Loader = branding_loader.BrandingLoader
PDF_Generator = report_lab_generator.PDF_Generator
bcrypt = auth.bcrypt

app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
app.secret_key = os.environ.get('APP_SECRET_KEY')
CORS(app) 

# Flask CLI
from app import cli as cli_commands
cli_commands.register_cli_commands(app)

# Payment Config
stripe_secret_key = os.environ.get('STRIPE_SECRET_KEY')
stripe_publishable_key = os.environ.get('STRIPE_PUBLISHABLE_KEY')
stripe_price_id = os.environ.get('STRIPE_PRICE_ID')
stripe.api_key = stripe_secret_key
payment_routes.PaymentRoutes = payment_routes.PaymentRoutes(app, stripe_publishable_key)

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
migrate = Migrate(app, db)

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

@app.route('/register', methods=['GET', 'POST'])
def register():
    schools = School.query.order_by(School.name).all()

    if request.method == 'POST':
        name = request.form.get('name')
        first_name, last_name = name.split(' ', 1) if ' ' in name else (name, '')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        school_name = request.form.get('school')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please log in.', 'warning')
            return redirect(url_for('login'))

        school = School.query.filter_by(name=school_name).first()
        if not school:
            flash('School not found. Please enter a valid school.', 'danger')
            return redirect(url_for('register'))

        school_domain = school.admin_email.split('@')[-1]
        if not email.endswith(f"@{school_domain}"):
            flash('Email does not match school domain. Please use a valid school email.', 'danger')
            return redirect(url_for('register'))

        if email == school.admin_email:
            role = 'admin'
        else:
            role = 'member'

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
            school_id=school.id,
            role=role
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('create_account.html', schools=schools)

@app.route('/schools', methods=['GET', 'POST'])
def schools():
    if request.method == 'POST':
        school_name = request.form.get('name')
        school_slug = request.form.get('slug')
        admin_email = request.form.get('admin_email')
        confirm_admin_email = request.form.get('confirm_admin_email')

        if School.query.filter_by(name=school_name).first():
            flash('School name already exists. Please choose a different name.', 'danger')
            return redirect(url_for('schools'))
        
        if admin_email != confirm_admin_email:
            flash('Admin email addresses do not match. Please confirm the admin email.', 'danger')
            return redirect(url_for('schools'))

        session['pending_school'] = {
            'name': school_name,
            'slug': school_slug,
            'admin_email': admin_email
        }

        try:
            checkout_session = stripe.checkout.Session.create(
                line_items=[{'price': stripe_price_id, 'quantity': 1}],
                mode='subscription',
                ui_mode='embedded',
                return_url='http://localhost:5000/return?session_id={CHECKOUT_SESSION_ID}',
                metadata=session['pending_school'],
                customer_email=session['pending_school']['admin_email']
            )
            return redirect(url_for('embedded_checkout', client_secret=checkout_session.client_secret))
        except Exception as e:
            print(str(e))
            flash('Could not start checkout. Please try again.', 'danger')
            return redirect(url_for('schools'))

        '''
        TODO: Redirect to school management page with option to subscribe if payment fails, instead of redirecting back to school creation form. This will allow users to create their school and then subscribe at a later time if they want.
        '''

    return render_template('schools.html')

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

@app.route("/terms")
def terms():
    return render_template('terms.html')

@app.route("/account")
@login_required
def account():
    branding = Branding_Loader.get_branding(current_user.school.slug)
    logo_path = f"/storage/schools/{current_user.school.slug}/assets/logo.png"
    return render_template('account.html', branding=branding, logo_path=logo_path)

@app.route("/subscription")
@login_required
def subscription():
    # Only the school's admin email may access this page
    if current_user.email != current_user.school.admin_email:
        flash('You do not have permission to access that page.', 'danger')
        return redirect(url_for('dashboard'))
    from datetime import datetime
    branding = Branding_Loader.get_branding(current_user.school.slug)
    logo_path = f"/storage/schools/{current_user.school.slug}/assets/logo.png"
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
            app.logger.error(f"Error fetching invoices: {e}")
    return render_template('subscription.html', branding=branding, logo_path=logo_path, invoices=invoices)

# ****** API Endpoints ******
@app.route("/api/account/password", methods=['POST'])
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
    except Exception as e:
        app.logger.error(f"Error updating password: {e}")
        return jsonify({'error': 'Failed to update password.'}), 500

@app.route("/api/account/information", methods=['POST'])
@login_required
def update_information():
    data = request.get_json()
    first_name = data.get('name').split(' ')[0] if data.get('name') else current_user.first_name
    last_name = data.get('name').split(' ')[1] if data.get('name') else current_user.last_name
    email = data.get('email')

    if not first_name or not last_name or not email:
        return jsonify({'error': 'Please fill in all fields.'}), 400

    try:
        if email != current_user.email:
            Auth.update_email(current_user, email)
        if first_name != current_user.first_name or last_name != current_user.last_name:
            Auth.update_name(current_user, first_name, last_name)
        return jsonify({'message': 'Information updated successfully.'}), 200
    except Exception as e:
        app.logger.error(f"Error updating information: {e}")
        return jsonify({'error': 'Failed to update information.'}), 500

@app.route("/api/account/delete", methods=['POST'])
@login_required
def delete_account():
    data = request.get_json()
    confirm = data.get('confirm')

    if confirm != 'DELETE':
        return jsonify({'error': 'Please type DELETE to confirm account deletion.'}), 400

    if current_user.email == current_user.school.admin_email:
        return jsonify({'error': 'The administrator account cannot be deleted. Please cancel subscription or change administrator if you wish to delete your school and all associated accounts.'}), 400

    try:
        user_id = current_user.id
        logout_user()
        user = User.query.get(user_id)
        db.session.delete(user)
        db.session.commit()
        return jsonify({'message': 'Account deleted successfully.'}), 200
    except Exception as e:
        app.logger.error(f"Error deleting account: {e}")
        return jsonify({'error': 'Failed to delete account.'}), 500

@app.route("/api/subscription/cancel", methods=['POST'])
@login_required
def cancel_subscription():
    if not current_user.school.stripe_subscription_id:
        return jsonify({'message': 'This is a permanent subscription and cannot be cancelled.', 'permanent': True}), 200

    if current_user.email != current_user.school.admin_email:
        return jsonify({'error': 'Only the school administrator can cancel the subscription.'}), 403
    
    try:
        stripe.Subscription.modify(
            current_user.school.stripe_subscription_id,
            cancel_at_period_end=True
        )
        current_user.school.stripe_subscription_status = 'canceled'
        db.session.commit()
        return jsonify({'message': 'Subscription cancelled successfully.'}), 200
    except Exception as e:
        app.logger.error(f"Error cancelling subscription: {e}")
        return jsonify({'error': 'Failed to cancel subscription.'}), 500

@app.route("/api/subscription/start", methods=['POST'])
@login_required
def start_subscription():
    if current_user.email != current_user.school.admin_email:
        return jsonify({'error': 'Only the school administrator can manage the subscription.'}), 403
    try:
        # If an existing subscription is still alive (just pending cancellation),
        # undo the cancellation instead of creating a new one
        if current_user.school.stripe_subscription_id:
            sub = stripe.Subscription.retrieve(current_user.school.stripe_subscription_id)
            if sub.status in ('active', 'trialing') and sub.cancel_at_period_end:
                stripe.Subscription.modify(
                    current_user.school.stripe_subscription_id,
                    cancel_at_period_end=False
                )
                current_user.school.stripe_subscription_status = sub.status
                db.session.commit()
                return jsonify({'reactivated': True, 'message': 'Subscription reactivated successfully.'}), 200

        # Subscription is truly gone — create a new checkout session
        checkout_session = stripe.checkout.Session.create(
            line_items=[{'price': stripe_price_id, 'quantity': 1}],
            mode='subscription',
            ui_mode='embedded',
            return_url=f'{request.host_url}return?session_id={{CHECKOUT_SESSION_ID}}',
            customer=current_user.school.stripe_customer_id or None,
            customer_email=None if current_user.school.stripe_customer_id else current_user.school.admin_email,
            metadata={'school_slug': current_user.school.slug}
        )
        return jsonify({'client_secret': checkout_session.client_secret}), 200
    except Exception as e:
        app.logger.error(f"Error starting subscription: {e}")
        return jsonify({'error': 'Failed to start subscription.'}), 500

@app.route("/api/subscription/settings", methods=['POST'])
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
        app.logger.error(f"Error updating school settings: {e}")
        return jsonify({'error': 'Failed to update settings.'}), 500

@app.route("/api/subscription/rebrand", methods=['POST'])
@login_required
def rebrand_subscription():
    import re
    data = request.get_json()
    colors = data.get('colors', {})

    required = {'primary', 'secondary', 'tertiary', 'dark', 'light', 'accent'}
    if not required.issubset(colors.keys()):
        return jsonify({'error': 'Missing required color tokens.'}), 400

    hex_re = re.compile(r'^#[0-9a-fA-F]{6}$')
    for token, value in colors.items():
        if not hex_re.match(value):
            return jsonify({'error': f'Invalid hex color for {token}: {value}'}), 400

    try:
        branding = Branding_Loader.get_branding(current_user.school.slug)
        branding['colors'] = colors
        Branding_Loader.update_branding(current_user.school.slug, branding)
        return jsonify({'message': 'Branding updated successfully.'}), 200
    except Exception as e:
        app.logger.error(f"Error updating branding: {e}")
        return jsonify({'error': 'Failed to update branding.'}), 500

LOGO_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOGO_ALLOWED_EXT = {'png', 'jpg', 'jpeg'}

@app.route('/api/subscription/logo', methods=['POST'])
@login_required
def upload_logo():
    from PIL import Image

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
        return jsonify({'error': 'File too large. Maximum size is 5 MB.'}), 400
    file.seek(0)

    try:
        img = Image.open(file).convert('RGBA')
    except Exception:
        return jsonify({'error': 'Invalid or corrupt image file.'}), 400

    try:
        assets_dir = os.path.join(app.config['STORAGE'], 'schools', current_user.school.slug, 'assets')
        os.makedirs(assets_dir, exist_ok=True)
        img.save(os.path.join(assets_dir, 'logo.png'), 'PNG')
        return jsonify({
            'message': 'Logo uploaded successfully.',
            'logo_url': f'/storage/schools/{current_user.school.slug}/assets/logo.png'
        }), 200
    except Exception as e:
        app.logger.error(f"Error saving logo: {e}")
        return jsonify({'error': 'Failed to save logo.'}), 500

roster_required_columns = {
    'Trackman ID': 'string', 
    'First Name': 'string',
    'Last Name': 'string',
    'Birthday': 'string',
    'Height': 'string',
    'Weight': 'numeric'
}

@app.route('/api/subscription/roster', methods=['GET'])
@login_required
def get_roster():
    roster_path = os.path.join(app.config['STORAGE'], 'schools', current_user.school.slug, 'assets', 'roster.csv')
    if not os.path.exists(roster_path):
        return jsonify({'roster': [], 'columns': []}), 200
    try:
        df = pd.read_csv(roster_path).fillna('')
        if 'Trackman ID' in df.columns:
            df['Trackman ID'] = df['Trackman ID'].apply(
                lambda x: str(int(float(x))) if x != '' else ''
            )
        return jsonify({'roster': df.to_dict(orient='records'), 'columns': list(df.columns)}), 200
    except Exception as e:
        app.logger.error(f"Error reading roster: {e}")
        return jsonify({'error': 'Failed to read roster.'}), 500

@app.route('/api/subscription/roster', methods=['PUT'])
@login_required
def save_roster():
    data = request.get_json()
    rows = data.get('rows', [])
    columns = data.get('columns', [])
    if not columns:
        return jsonify({'error': 'No columns provided.'}), 400
    try:
        df = pd.DataFrame(rows if rows else [], columns=columns)
        assets_dir = os.path.join(app.config['STORAGE'], 'schools', current_user.school.slug, 'assets')
        os.makedirs(assets_dir, exist_ok=True)
        df.to_csv(os.path.join(assets_dir, 'roster.csv'), index=False)
        return jsonify({'message': 'Roster saved successfully.'}), 200
    except Exception as e:
        app.logger.error(f"Error saving roster: {e}")
        return jsonify({'error': 'Failed to save roster.'}), 500

@app.route('/api/subscription/roster/pfp/<player_id>', methods=['POST'])
@login_required
def upload_player_pfp(player_id):
    import re
    from PIL import Image
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
        return jsonify({'error': 'File too large. Maximum size is 5 MB.'}), 400
    file.seek(0)
    try:
        img = Image.open(file).convert('RGBA')
    except Exception:
        return jsonify({'error': 'Invalid or corrupt image file.'}), 400
    try:
        player_dir = os.path.join(app.config['STORAGE'], 'schools', current_user.school.slug, 'assets', 'players', player_id)
        os.makedirs(player_dir, exist_ok=True)
        img.save(os.path.join(player_dir, 'pfp.png'), 'PNG')
        return jsonify({
            'message': 'Profile picture uploaded successfully.',
            'pfp_url': f'/storage/schools/{current_user.school.slug}/assets/players/{player_id}/pfp.png'
        }), 200
    except Exception as e:
        app.logger.error(f"Error saving player pfp: {e}")
        return jsonify({'error': 'Failed to save profile picture.'}), 500

@app.route('/api/subscription/roster/pfp/bulk', methods=['POST'])
@login_required
def upload_player_pfp_bulk():
    import re
    import unicodedata
    from PIL import Image

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files provided.'}), 400

    roster_path = os.path.join(app.config['STORAGE'], 'schools', current_user.school.slug, 'assets', 'roster.csv')
    if not os.path.exists(roster_path):
        return jsonify({'error': 'No roster found. Please upload a roster first.'}), 400

    roster_df = pd.read_csv(roster_path)

    def normalize(s):
        s = unicodedata.normalize('NFD', str(s).lower())
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        return re.sub(r'[^a-z]', '', s)

    name_to_id = {}
    for _, row in roster_df.iterrows():
        first = normalize(row.get('First Name', ''))
        last = normalize(row.get('Last Name', ''))
        player_id = str(row.get('Trackman ID', '')).strip()
        if first and last and player_id:
            name_to_id[first + last] = player_id
            name_to_id[last + first] = player_id

    print("name_to_id:", name_to_id)

    matched, unmatched = [], []

    for file in files:
        if not file.filename:
            continue
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in LOGO_ALLOWED_EXT:
            unmatched.append(file.filename)
            continue

        basename = file.filename.replace('\\', '/').split('/')[-1]
        stem = normalize(os.path.splitext(basename)[0])
        print(f"file: {file.filename}  stem: {stem}  match: {name_to_id.get(stem)}")
        player_id = name_to_id.get(stem)
        if not player_id:
            unmatched.append(file.filename)
            continue

        file.seek(0, 2)
        too_large = file.tell() > LOGO_MAX_BYTES
        file.seek(0)
        if too_large:
            print(f"!!! PFP TOO LARGE {file.filename}: {file.tell()} bytes")
            unmatched.append(file.filename)
            continue

        try:
            img = Image.open(file).convert('RGBA')
            player_dir = os.path.join(app.config['STORAGE'], 'schools', current_user.school.slug, 'assets', 'players', player_id)
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

@app.route('/api/subscription/roster', methods=['POST'])
@login_required
def upload_roster():
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
        df = pd.read_csv(filepath)[['Trackman ID', 'First Name', 'Last Name', 'Birthday', 'Height', 'Weight']]
    elif filepath.endswith('.xlsx') or filepath.endswith('.xls'):
        df = pd.read_excel(filepath)[['Trackman ID', 'First Name', 'Last Name', 'Birthday', 'Height', 'Weight']]
    else:
        try: 
            os.remove(filepath)
        except:
            pass
        return jsonify({'error': 'Unsupported file format. Please provide a .csv, .xlsx, or .xls file.'}), 400

    is_valid, result = file_validator.validate_uploaded_file(
        source_df=df,
        file=file,
        filepath=filepath,
        required_columns=list(roster_required_columns.keys()),
        column_types=roster_required_columns
    )

    if not is_valid:
        try: 
            os.remove(filepath)
        except:
            pass
        return jsonify({'error': result}), 400
    
    checksum = result
    app.logger.info(f"Valid roster file uploaded: {filename} - Checksum: {checksum}")

    try:
        assets_dir = os.path.join(app.config['STORAGE'], 'schools', current_user.school.slug, 'assets')
        os.makedirs(assets_dir, exist_ok=True)
        roster_path = os.path.join(assets_dir, 'roster.csv')
        df.to_csv(roster_path, index=False)
        os.remove(filepath)
        return jsonify({
            'message': 'Roster uploaded and processed successfully.',
            'roster_url': f'/storage/schools/{current_user.school.slug}/assets/roster.csv'
        }), 200
    except Exception as e:
        app.logger.error(f"Error saving roster: {e}")
        return jsonify({'error': 'Failed to save roster.'}), 500

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

    if filepath.endswith('.csv'):
        source_df = pd.read_csv(filepath)
    elif filepath.endswith('.xlsx') or filepath.endswith('.xls'):
        source_df = pd.read_excel(filepath)
    else: 
        raise ValueError("Unsupported file format. Please provide a .csv, .xlsx, or .xls file.")

    is_valid, result = file_validator.validate_uploaded_file(
        source_df=source_df,
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

        # Roster df
        roster = pd.read_csv(os.path.join(app.config['STORAGE'], 'schools', current_user.school.slug, 'assets', 'roster.csv')) if os.path.exists(os.path.join(app.config['STORAGE'], 'schools', current_user.school.slug, 'assets', 'roster.csv')) else pd.DataFrame()

        gen = PDF_Generator(
            current_user=current_user,
            branding=branding)

        # Create list of report data
        reports = []
        for pitcher_id in source_df['PitcherId'].unique():
            if source_df.loc[source_df['PitcherId'] == pitcher_id, 'PitcherTeam'].iloc[0] != current_user.school.trackman_id:
                continue

            if current_user.school.is_active:
                # Generate heat map
                report.pitch_heat_map_by_batter_side(source_df, current_user.id, school_temp_folder, pitcher_id, 0.75)
                report.pitch_break_map(source_df, current_user.id, school_temp_folder, pitcher_id, 0.75)

            if pitcher_id not in roster['Trackman ID'].values:
                last_name, first_name = source_df.loc[source_df['PitcherId'] == pitcher_id, 'Pitcher'].iloc[0].split(', ', 1)
                roster = pd.concat([roster, pd.DataFrame([{'Trackman ID': pitcher_id, 'First Name': first_name, 'Last Name': last_name}])], ignore_index=True)

            # Build table data
            table_data = report.build_table(source_df, pitcher_id)
            if not table_data or len(table_data) < 2 or table_data[1] is None:
                raise ValueError(f'Failed to build table data for pitcher ID {pitcher_id}')
            report_html = table_data[4].to_html(index=False, float_format='%.2f', border=0, classes='pitcher-data-table', escape=False, justify='left', na_rep='')

            # Pitch Usage table data
            pitch_usage_data = report.usage_table(source_df, pitcher_id)
            if not pitch_usage_data or len(pitch_usage_data) < 2 or pitch_usage_data[1] is None:
                raise ValueError(f'Failed to build pitch usage table data for pitcher ID {pitcher_id}')
            left_usage_html = pitch_usage_data[0].to_html(index=False, float_format='%.2f', border=0, classes='pitch-usage-table', escape=False, justify='left', na_rep='')
            right_usage_html = pitch_usage_data[1].to_html(index=False, float_format='%.2f', border=0, classes='pitch-usage-table', escape=False, justify='left', na_rep='')

            year = table_data[0].split('-')[0]
            month = table_data[0].split('-')[1]
            day = table_data[0].split('-')[2]

            date = month + '/' + day + '/' + year
            away_team = table_data[2]
            home_team = table_data[1]

            # Add to reports list
            reports.append({
                'pitcher_id': str(pitcher_id),
                'pitcher_name': table_data[3],
                'pitcher_table': report_html,
                'left_usage_table': left_usage_html,
                'right_usage_table': right_usage_html,
                'heatmap_url': f'/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_heat_map.png',
                'breakmap_url': f'/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_break_map.png',
                'pdf_url': f'/storage/schools/{current_user.school.slug}/reports/{current_user.id}_pitcher_{pitcher_id}_report.pdf'
            })

            # Generate PDF report
            _report = {
                'pitcher_name': table_data[3],
                'pitcher_id': str(pitcher_id),
                'date': date,
                'home_team': home_team,
                'away_team': away_team,
                'pitch_stats': table_data[4],
                'pitch_usage_left': pitch_usage_data[0],
                'pitch_usage_right': pitch_usage_data[1],
                'pitch_heat_map': os.path.join(school_temp_folder, f'{current_user.id}_pitcher_{pitcher_id}_heat_map.png'),
                'pitch_break_map': os.path.join(school_temp_folder, f'{current_user.id}_pitcher_{pitcher_id}_break_map.png'),
            }

            gen.generate_pitcher_report(_report, os.path.abspath(os.path.join(school_output_folder, f'{current_user.id}_pitcher_{pitcher_id}_report.pdf')))

            del table_data
            del report_html
            gc.collect()

        roster.to_csv(os.path.join(app.config['STORAGE'], 'schools', current_user.school.slug, 'assets', 'roster.csv'), index=False)

        # Merge all PDFs into one
        merged_pdf_path = os.path.join(school_output_folder, f'{current_user.id}_merged_pitcher_reports.pdf')
        report_lab_generator.merge_pdfs(current_user.id, school_output_folder, merged_pdf_path)

        return jsonify({
            'message': 'File processed successfully',
            'num_reports': len(reports),
            'reports': reports,
            'merged_pdf_url': f'/storage/schools/{current_user.school.slug}/reports/{current_user.id}_merged_pitcher_reports.pdf',
            'game_data' : {
                'date': date,
                'home_team': home_team,
                'away_team': away_team,
            },
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

def active_subscription_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not current_user.school.is_active:
            flash('Your school does not have an active subscription. Please contact your administrator.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

if __name__ == '__main__':
    app.run()