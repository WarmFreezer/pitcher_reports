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
from typing import Any

from flask import Flask, send_from_directory, render_template
from flask.typing import ResponseReturnValue
from flask_cors import CORS
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, login_required

from app.db.models import db, User
from app.services.branding_loader import BrandingLoader
from app.routes.payments import payment_bp

from app.routes.auth import auth_bp
from app.routes.pages import pages_bp
from app.routes.account import account_bp
from app.routes.batting import batting_bp
from app.routes.catching import catching_bp
from app.routes.pitching import pitching_bp
from app.routes.subscription import subscription_bp
from app.routes.upload import upload_bp
from app.routes.master import master_bp

STORAGE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storage')


def create_app(config_overrides: dict | None = None) -> Flask:
    """Flask application factory: wires up the DB, login manager, and blueprints."""
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

    if config_overrides:
        app.config.update(config_overrides)

    os.makedirs(app.config['STORAGE'], exist_ok=True)
    db.init_app(app)
    Migrate(app, db)

    # Login manager
    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        return db.session.get(User, int(user_id))

    # Context processor
    @app.context_processor
    def inject_branding() -> dict[str, Any]:
        """Make the current school's branding/logo available to every template."""
        if current_user.is_authenticated and current_user.school:
            branding = BrandingLoader.get_branding(current_user.school_id)
            logo_path = BrandingLoader.get_logo_path(current_user.school_id)
            return {'branding': branding, 'logo_path': logo_path}
        return {}

    # Static file serving
    @app.route('/favicon.ico')
    def favicon() -> ResponseReturnValue:
        return send_from_directory(os.path.join(str(app.static_folder), 'resources'), 'favicon.ico', mimetype='image/x-icon')

    @app.route('/robots.txt')
    def robots() -> ResponseReturnValue:
        return send_from_directory(str(app.static_folder), 'robots.txt', mimetype='text/plain')

    @app.route('/.well-known/security.txt')
    def security() -> ResponseReturnValue:
        return send_from_directory(str(app.static_folder), 'security.txt', mimetype='text/plain')

    @app.errorhandler(404)
    def not_found(e: Exception) -> ResponseReturnValue:
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def server_error(e: Exception) -> ResponseReturnValue:
        return render_template('500.html'), 500

    # Anything not belonging to the caller's own school resolves 404 rather than
    # 403, matching _selected_games() in routes/pitching.py -- a probe can't
    # distinguish "not yours" from "does not exist".
    def _require_own_school(school_id: int) -> ResponseReturnValue | None:
        if not current_user.is_authenticated or school_id != current_user.school_id:
            return render_template('404.html'), 404
        return None

    @app.route('/storage/schools/<int:school_id>/assets/<path:filename>')
    @login_required
    def school_files(school_id: int, filename: str) -> ResponseReturnValue:
        if (denied := _require_own_school(school_id)) is not None:
            return denied
        return send_from_directory(os.path.join(app.config['STORAGE'], 'schools', str(school_id), 'assets'), filename)

    @app.route('/storage/schools/<int:school_id>/temp/<path:filename>')
    @login_required
    def school_temp_files(school_id: int, filename: str) -> ResponseReturnValue:
        if (denied := _require_own_school(school_id)) is not None:
            return denied
        return send_from_directory(os.path.join(app.config['STORAGE'], 'schools', str(school_id), 'temp'), filename)

    @app.route('/storage/schools/<int:school_id>/reports/<path:filename>')
    @login_required
    def school_report_files(school_id: int, filename: str) -> ResponseReturnValue:
        if (denied := _require_own_school(school_id)) is not None:
            return denied
        return send_from_directory(os.path.join(app.config['STORAGE'], 'schools', str(school_id), 'reports'), filename)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(batting_bp)
    app.register_blueprint(pitching_bp)
    app.register_blueprint(catching_bp)
    app.register_blueprint(subscription_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(master_bp)

    return app


app = create_app()

if __name__ == '__main__':
    app.run()
