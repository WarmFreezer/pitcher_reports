from datetime import date
from flask import Blueprint, render_template, redirect, url_for, jsonify, session, request, make_response
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
    logo_path = f"/storage/schools/{current_user.school.slug}/assets/logo.png"
    return render_template('index.html', logo_path=logo_path)


@pages_bp.route('/about')
def about():
    return render_template('about.html')


@pages_bp.route('/terms')
def terms():
    return render_template('terms.html')


@pages_bp.route('/sitemap.xml')
def sitemap():
    base = request.host_url.rstrip('/')
    today = date.today().isoformat()

    pages = [
        {'loc': f'{base}/',         'priority': '1.0', 'changefreq': 'weekly'},
        {'loc': f'{base}/about',    'priority': '0.8', 'changefreq': 'monthly'},
        {'loc': f'{base}/schools',  'priority': '0.8', 'changefreq': 'monthly'},
        {'loc': f'{base}/register', 'priority': '0.7', 'changefreq': 'monthly'},
        {'loc': f'{base}/login',    'priority': '0.6', 'changefreq': 'monthly'},
        {'loc': f'{base}/terms',    'priority': '0.5', 'changefreq': 'monthly'},
    ]

    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for page in pages:
        xml_lines += [
            '  <url>',
            f'    <loc>{page["loc"]}</loc>',
            f'    <lastmod>{today}</lastmod>',
            f'    <changefreq>{page["changefreq"]}</changefreq>',
            f'    <priority>{page["priority"]}</priority>',
            '  </url>',
        ]
    xml_lines.append('</urlset>')

    response = make_response('\n'.join(xml_lines))
    response.headers['Content-Type'] = 'application/xml'
    return response


@pages_bp.route('/api/toasts')
def get_toasts():
    toasts = session.pop('_toasts', [])
    return jsonify(toasts)
