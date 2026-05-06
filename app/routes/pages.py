from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    # Authenticated users go straight to the dashboard
    if current_user.is_authenticated:
        return redirect(url_for('pages.dashboard'))
    return redirect(url_for('auth.login'))


@pages_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')


@pages_bp.route('/upload')
@login_required
def upload_page():
    return render_template('index.html')


@pages_bp.route('/about')
def about():
    return render_template('about.html')


@pages_bp.route('/terms')
def terms():
    return render_template('terms.html')
