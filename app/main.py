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
from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_migrate import Migrate
from flask_login import LoginManager, current_user

from app.db.models import db, User
from app.services.branding_loader import BrandingLoader
from app.routes.payments import payment_bp

from app.routes.auth import auth_bp
from app.routes.pages import pages_bp
from app.routes.account import account_bp
from app.routes.subscription import subscription_bp
from app.routes.upload import upload_bp

STORAGE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storage')

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('APP_SECRET_KEY')
CORS(app)

# Flask CLI
from app import cli as cli_commands
cli_commands.register_cli_commands(app)

# Database
database_url = os.environ.get('DATABASE_URL', 'sqlite:///pitcher_reports.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SECRET_KEY'] = app.secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['STORAGE'] = STORAGE_FOLDER

os.makedirs(STORAGE_FOLDER, exist_ok=True)
db.init_app(app)
migrate = Migrate(app, db)

# Login manager
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Context processor
@app.context_processor
def inject_branding():
    if current_user.is_authenticated:
        branding = BrandingLoader.get_branding(current_user.school.slug)
        logo_path = BrandingLoader.get_logo_path(current_user.school.slug)
        return {'branding': branding, 'logo_path': logo_path}
    return {}

# Static file serving
@app.route('/storage/schools/<school_slug>/assets/<path:filename>')
def school_files(school_slug, filename):
    return send_from_directory(os.path.join(app.config['STORAGE'], 'schools', school_slug, 'assets'), filename)

@app.route('/storage/schools/<school_slug>/temp/<path:filename>')
def school_temp_files(school_slug, filename):
    return send_from_directory(os.path.join(app.config['STORAGE'], 'schools', school_slug, 'temp'), filename)

@app.route('/storage/schools/<school_slug>/reports/<path:filename>')
def school_report_files(school_slug, filename):
    return send_from_directory(os.path.join(app.config['STORAGE'], 'schools', school_slug, 'reports'), filename)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(pages_bp)
app.register_blueprint(account_bp)
app.register_blueprint(subscription_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(payment_bp)

if __name__ == '__main__':
    app.run()
