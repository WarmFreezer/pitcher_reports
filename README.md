# Baseball Pitcher Report Generator

A Flask web application that generates comprehensive pitcher performance reports from TrackMan baseball data. Supports multiple schools with subscription-based access, custom branding, and professional PDF report generation.

Deployed on [Railway](https://railway.app) with automated SSL.

## Features

- **User Authentication** — Secure login with role-based access (admin / member)
- **Self-Service School Registration** — Schools sign up and subscribe via Stripe Embedded Checkout
- **Email Domain Validation** — User registration is restricted to the school's verified email domain
- **Subscription Gating** — Heat maps and break maps require an active Stripe subscription; table data is always available
- **Pitch Heat Maps** — Visualize pitch locations split by batter handedness (L/R)
- **Pitch Break Maps** — Visualize movement profiles for each pitcher
- **Pitch Usage Tables** — Per-pitch-type usage breakdowns vs. left and right-handed batters
- **Statistical Tables** — Detailed per-pitch-type performance metrics
- **PDF Reports** — Per-pitcher PDFs with school branding, plus a merged all-pitchers PDF
- **Custom Branding** — School-specific colors and logos
- **TrackMan Team Filtering** — Reports are scoped to the uploading school's TrackMan ID

## Tech Stack

- **Framework**: Flask 3.x
- **Database**: PostgreSQL (production) / SQLite (local dev), managed with Flask-Migrate
- **Auth**: Flask-Login + Flask-Bcrypt
- **PDF Generation**: ReportLab
- **Visualizations**: Matplotlib + Seaborn
- **Payments**: Stripe (Embedded Checkout + Webhooks)
- **Production Server**: Gunicorn
- **Deployment**: Railway

## Local Development

### 1. Clone the repository

```bash
git clone https://github.com/WarmFreezer/pitcher_reports.git
cd pitcher_reports
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
APP_SECRET_KEY=your-secret-key

# Database (omit to use SQLite locally)
DATABASE_URL=postgresql://user:pass@localhost/pitcher_reports

# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_PRICE_ID=price_...
STRIPE_WHSEC=whsec_...

```

### 5. Initialize the database

```bash
flask --app app.main db upgrade
```

### 6. Run the development server

```bash
flask --app app.main run
```

Navigate to `http://127.0.0.1:5000`.

## Usage

### Registering a School

1. Go to `/schools` and fill in the school name, slug, and admin email
2. Complete the Stripe Embedded Checkout to activate the subscription
3. After payment, you are redirected to create the first (admin) user account

### Registering Users

1. Go to `/register`
2. Enter a name, email (must match the school's domain), and password
3. The user whose email matches `school.admin_email` is granted the `admin` role; all others receive `member`

### Uploading Data and Generating Reports

1. Log in and navigate to the Upload page
2. Upload a TrackMan export file (`.xlsx`, `.xls`, or `.csv`)
3. The app filters pitchers by the school's `trackman_id`
4. Reports render inline; individual and merged PDFs are available for download

## School Branding

Branding is defined in `app/storage/schools/{slug}/assets/branding.json`:

```json
{
    "school": {
        "name": "School Name",
        "short_name": "Short Name",
        "mascot": "Mascot",
        "slug": "school_slug"
    },
    "colors": {
        "primary": "#0033A0",
        "secondary": "#FFCF00",
        "tertiary": "#001D39",
        "dark": "#343434",
        "light": "#ECECEC",
        "accent": "#005EB8"
    },
    "logos": {
        "primary": "assets/logo.png"
    },
    "typography": {
        "font_family": "Graduate, sans-serif"
    },
    "report_settings": {
        "header_height_px": 120,
        "show_logo": true,
        "footer_text": "© 2025 School Name. All rights reserved."
    }
}
```

School logos are loaded from `app/storage/schools/{slug}/assets/logo.png`.

## CLI Commands

```bash
# Database
flask --app app.main db upgrade          # Run pending migrations
flask --app app.main init-db             # Create tables (dev only)
flask --app app.main reset-db            # Drop and recreate all tables (destructive)

# Schools
flask --app app.main create-school-func NAME SLUG PRIMARY SECONDARY TERTIARY ACCENT LIGHT DARK
flask --app app.main list-schools

# Users
flask --app app.main create-user-func EMAIL PASSWORD [--first-name X] [--last-name Y] [--school-id N] [--role admin|member]
flask --app app.main list-users
```

## Required Data Format

TrackMan exports must include these columns:

| Column | Description |
|---|---|
| `Pitcher` | Pitcher name |
| `PitcherId` | Unique pitcher identifier |
| `PitcherTeam` | Team ID (matched against school's `trackman_id`) |
| `TaggedPitchType` | Pitch type label |
| `PlateLocHeight` | Vertical plate location |
| `PlateLocSide` | Horizontal plate location |
| `BatterSide` | `Left` or `Right` |

Accepted formats: `.xlsx`, `.xls`, `.csv`

## Deployment

The app is deployed on Railway. Key production configuration:

- `DATABASE_URL` — Railway-provided PostgreSQL connection string (automatically rewritten from `postgres://` to `postgresql://`)
- SSL is provisioned automatically by Railway
- `gunicorn` is the production WSGI server

## File Structure

```
pitcher_reports/
├── app/
│   ├── main.py                     # Flask app + routes
│   ├── cli.py                      # Flask CLI commands
│   ├── payment_routes.py           # Stripe checkout + webhook routes
│   ├── db/
│   │   ├── models.py               # SQLAlchemy models (School, User)
│   │   └── session.py
│   ├── services/
│   │   ├── auth.py
│   │   ├── branding_loader.py
│   │   ├── file_validator.py
│   │   ├── report.py               # Data processing + visualizations
│   │   └── report_lab_generator.py # ReportLab PDF generation
│   ├── static/
│   ├── storage/
│   │   └── schools/{slug}/
│   │       ├── assets/             # branding.json, local logo fallback
│   │       ├── temp/               # Heat map + break map images (per-user)
│   │       └── reports/            # Generated PDFs (per-user)
│   └── templates/
├── migrations/                     # Alembic migration files
├── requirements.txt
└── README.md
```

## License

This project is source-available for non-commercial use only. Commercial licensing available upon request.

University logos, seals, and trademarks are the property of their respective institutions and are not licensed for reuse or redistribution.

## Contact

Thomas Eubank — [thomas.eubank516@gmail.com](mailto:thomas.eubank516@gmail.com)

Project Link: [https://github.com/WarmFreezer/pitcher_reports](https://github.com/WarmFreezer/pitcher_reports)
