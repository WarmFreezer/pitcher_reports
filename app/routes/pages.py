from datetime import date
from flask import Blueprint, render_template, redirect, url_for, jsonify, session, request, make_response
from flask_login import login_required, current_user
from sqlalchemy import func

from app.db.models import db
from app.db import models

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


@pages_bp.route('/api/team/overview')
@login_required
def team_overview():
    rows = db.session.query(
        models.Pitcher.id.label("pitcher_id"),
        models.Pitcher.name.label("pitcher_name"),
        func.sum(models.Outing.pitch_count).label("total_pitches"),
        func.sum(models.Outing.lo_inning_count).label("total_lo_inning_count"),
        func.sum(models.Outing.lo_reach).label("total_lo_reach"),
        (func.sum(models.Outing.lo_reach) / func.nullif(func.sum(models.Outing.lo_inning_count), 0)).label("lo_obp"),
        func.sum(models.Outing.lo_bb_count).label("total_lo_bb_count"),
        (func.sum(models.Outing.lo_bb_count) / func.nullif(func.sum(models.Outing.lo_inning_count), 0)).label("lo_bb_percentage"),
        func.sum(models.Outing.two_out_ab_count).label("total_two_out_ab_count"),
        func.sum(models.Outing.two_out_reach).label("total_two_out_reach"),
        (func.sum(models.Outing.two_out_reach) / func.nullif(func.sum(models.Outing.two_out_ab_count), 0)).label("two_out_eff_percentage"),
        func.sum(models.Outing.two_out_bb_count).label("total_two_out_bb_count"),
        (func.sum(models.Outing.two_out_bb_count) / func.nullif(func.sum(models.Outing.two_out_ab_count), 0)).label("two_out_bb_percentage"),
    ).join(models.Outing, models.Outing.pitcher_id == models.Pitcher.id
    ).filter(
        models.Pitcher.school_id == current_user.school_id
    ).group_by(
        models.Pitcher.id,
        models.Pitcher.name
    ).all()

    results = [{
        'pitcher_id':              row.pitcher_id,
        'pitcher_name':            row.pitcher_name,
        'total_pitches':           row.total_pitches,
        'total_lo_inning_count':   row.total_lo_inning_count,
        'total_lo_reach':          row.total_lo_reach,
        'lo_obp':                  row.lo_obp,
        'total_lo_bb_count':       row.total_lo_bb_count,
        'lo_bb_percentage':        row.lo_bb_percentage,
        'total_two_out_ab_count':  row.total_two_out_ab_count,
        'total_two_out_reach':     row.total_two_out_reach,
        'two_out_eff_percentage':  row.two_out_eff_percentage,
        'total_two_out_bb_count':  row.total_two_out_bb_count,
        'two_out_bb_percentage':   row.two_out_bb_percentage,
    } for row in rows]

    return jsonify(results)

@pages_bp.route('/api/pitcher/<int:pitcher_id>/averages')
@login_required
def pitcher_averages(pitcher_id):
    pitcher = db.session.get(models.Pitcher, pitcher_id)
    if not pitcher:
        return jsonify({'error': 'Pitcher not found'}), 404

    rows = db.session.query(
        models.Pitch_Types.abbreviation.label("pitch_type_abbreviation"),
        func.sum(models.Outing_Pitch_Stat.count).label("tot_count"),
        func.sum(models.Outing_Pitch_Stat.strike_count).label("tot_strike_count"),
        (func.sum(models.Outing_Pitch_Stat.strike_count) / func.nullif(func.sum(models.Outing_Pitch_Stat.count), 0)).label("strike_percentage"),
        (func.sum(models.Outing_Pitch_Stat.sw_miss_count) / func.nullif(func.sum(models.Outing_Pitch_Stat.count), 0)).label("sw_percentage"),
        (func.sum(models.Outing_Pitch_Stat.sw_miss_count) / func.nullif(func.sum(models.Outing_Pitch_Stat.sw_percentage * models.Outing_Pitch_Stat.count), 0)).label("sw_miss_percentage"),
        (func.sum(models.Outing_Pitch_Stat.ip_count) / func.nullif(func.sum(models.Outing_Pitch_Stat.count), 0)).label("ip_percentage"),
        func.avg(models.Outing_Pitch_Stat.low_quartile_speed).label("avg_low_quartile_speed"),
        func.avg(models.Outing_Pitch_Stat.median_speed).label("avg_median_speed"),
        func.avg(models.Outing_Pitch_Stat.high_quartile_speed).label("avg_high_quartile_speed"),
    ).join(models.Pitch_Types, models.Outing_Pitch_Stat.pitch_type_id == models.Pitch_Types.id
    ).filter(
        models.Outing_Pitch_Stat.pitcher_id == pitcher_id
    ).group_by(
        models.Outing_Pitch_Stat.pitch_type_id,
        models.Pitch_Types.abbreviation
    ).all()

    results = [{
        'pitch_type':            row.pitch_type_abbreviation,
        'tot_count':             row.tot_count,
        'tot_strike_count':      row.tot_strike_count,
        'strike_percentage':     row.strike_percentage,
        'sw_percentage':         row.sw_percentage,
        'sw_miss_percentage':    row.sw_miss_percentage,
        'ip_percentage':         row.ip_percentage,
        'avg_low_quartile_speed': row.avg_low_quartile_speed,
        'avg_median_speed':      row.avg_median_speed,
        'avg_high_quartile_speed': row.avg_high_quartile_speed,
    } for row in rows]

    return jsonify(results)


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


@pages_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')


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
