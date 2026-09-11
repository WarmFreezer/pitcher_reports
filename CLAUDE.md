# Project Overview
Pitcher analytics web app. Flask/PostgreSQL/Docker deployed on Railway.
School-scoped SaaS — every query must filter by school_id via the logged-in user.

# Stack
- Backend: Flask, SQLAlchemy, Flask-Login
- DB: PostgreSQL on Railway, SQLite for debug
- Frontend: Jinja2 templates
- PDF generation: ReportLab

# Database Conventions
- Never aggregate in Python — always push SUM/AVG/COUNT to the DB via SQLAlchemy func
- Rate stats (percentages) use totals: SUM(strikes) / SUM(count), never AVG(strike_percentage)
- Measurement stats (velo, spin) use AVG
- Use db.session.get(Model, id) not Model.query.get(id) — the latter is deprecated
- Always use func.nullif(denominator, 0) to guard against division by zero

# Schema Summary
schools → pitchers (school_id FK) → outing_pitch_stats (pitcher_id FK)
                                   → outings (pitcher_id FK)
pitch_types — lookup table, join via pitch_type_id

# Key Rules
- Never return data across school boundaries — filter by current_user.school_id
- No N+1 queries — use GROUP BY with joins instead of looping and querying per pitcher