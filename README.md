# Stat_Line — Baseball Analytics for College Programs

**Live at [stat-line.app](https://stat-line.app)**

Turn a raw TrackMan export into branded, coach-ready reports in about the time it takes to walk from the field to the office.

Stat_Line is a hosted, school-scoped web application. Your staff uploads a game file; the app returns pitch heat maps, movement profiles, hitter spray charts, plate-discipline tables, and print-ready PDFs carrying your school's colors and logo. Data from one program is never visible to another.

Deployed on [Railway](https://railway.app) with automated SSL.

---

## What it does for your program

### Turn a game file into a report before the bus leaves

A TrackMan export is thousands of rows nobody reads. Upload it and Stat_Line returns one row per pitch type, ranked by usage:

| Group | Columns |
|---|---|
| **Usage** | `Thrown` — share of total pitches |
| **Velocity band** | `Low` / `Vel.` / `High` — the range, not just the average, so you can see a tiring arm |
| **Movement** | `IVB`, `HB` — induced vertical and horizontal break |
| **Spin** | `Spin` rate and `Axis` — spin direction as a clock face |
| **Approach** | `VAA`, `HAA` — vertical and horizontal approach angle |
| **Release** | `RelH`, `RelS`, `Ext.` — height, side, and extension |
| **Results** | `Zone%`, `Chase%`, `CSW%` |

Alongside the table: heat maps split by batter handedness, and a break map showing the whole arsenal at a glance with the pitcher's arm angle computed from it. Every pitcher gets an individual PDF, plus one merged file for the whole staff.

You also get pitch usage broken out separately against left- and right-handed batters, which is where platoon problems show up first.

You can point the same file at the other dugout. Flip to **Opponent** and the app builds the identical report for the arms your hitters are about to face.

### Scout hitters across a time frame, not just a game

One game tells you very little about a hitter. The **Batting** page works across your saved game archive: choose a hitter and a date range, and the report is built from every game in that window.

- **Spray charts split by pitcher handedness** — where the ball actually lands, sized by exit velocity and shaped by batted-ball type, so pull tendencies and platoon splits are visible at a glance
- **Slash line and batted-ball profile** — AVG / OBP / SLG / OPS, hard-hit rate, average and max exit velocity, launch angle, ground-ball and fly-ball mix
- **Plate discipline by pitch type** — swing, whiff, chase, and contact rates, so you can see which pitch is actually beating a hitter

Point it at opponents to build a defensive positioning card, or at your own roster to track a swing change over the back half of a season.

### Track development over a season, not just a start

Saved games roll into a team dashboard: per-pitcher averages across every outing, situational splits for lead-off and two-out effectiveness, and a team-wide overview table. Anything on the dashboard exports to Excel for staff who would rather work in a spreadsheet.

### Reports that look like they came from your program

Every PDF and every page carries your colors, your logo, and your players' photos. Upload a roster CSV, drop in headshots individually or in bulk, and set your palette from the subscription page with a live preview before you commit. Reports you hand a recruit or a parent look like your program produced them, because it did.

### Built for a staff, not a single laptop

- **Multiple accounts per school** with admin and member roles
- **Self-service signup** — register the school, subscribe, and create the first admin account without waiting on anyone
- **Domain-restricted registration**, so only people with a school email address can join your program
- **Every query is scoped to your school.** Cross-program data access is prevented at the query layer and covered by a dedicated isolation test suite.

### Works with the data you already have

Stat_Line reads the TrackMan export as-is — `.csv`, `.xlsx`, or `.xls`, no reformatting. Uploads are validated on extension, MIME type, file signature, and column presence before anything is processed, so a wrong file gets a clear error rather than a broken report. Pitchers found in a game file but missing from your roster are added automatically.

---

## How a season runs

| Stage | What your staff does |
|---|---|
| **Setup, once** | Register the school, subscribe, set colors and logo, upload the roster |
| **After each game** | Upload the TrackMan file, review the reports, click **Save Game** |
| **Before a series** | Upload the opponent's file with **Opponent** selected; build hitter reports over a date range |
| **Through the season** | Watch the dashboard trends; export to Excel or PDF as needed |

**Save Game** is the step that matters most. It persists the outing to your database *and* archives the raw file, which is what makes date-ranged hitting reports possible later. A game that is uploaded but never saved produces reports for that day only.

---

## Access and subscriptions

Stat_Line is subscription-based, billed through Stripe Embedded Checkout.

Tables and statistics are always available. **Charts — heat maps, break maps, and spray charts — require an active subscription.** A lapsed subscription degrades the reports rather than locking you out: your numbers keep working.

---

## Tech Stack

- **Framework**: Flask 3.x
- **Database**: PostgreSQL (production) / SQLite (local dev), managed with Flask-Migrate
- **Auth**: Flask-Login + Flask-Bcrypt
- **PDF Generation**: ReportLab
- **Visualizations**: Matplotlib + Seaborn
- **Payments**: Stripe (Embedded Checkout + Webhooks)
- **Production Server**: Gunicorn
- **Deployment**: Railway

---

## Local Development

```bash
git clone https://github.com/WarmFreezer/pitcher_reports.git
cd pitcher_reports

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Mac/Linux

pip install -r requirements.txt
flask --app app.main db upgrade
flask --app app.main run
```

Navigate to `http://127.0.0.1:5000`. Omitting `DATABASE_URL` falls back to local SQLite.

Create a `.env` in the project root:

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

Run the test suite with `pytest`.

### CLI Commands

```bash
# Database
flask --app app.main db upgrade          # Run pending migrations
flask --app app.main init-db             # Create tables (dev only)
flask --app app.main reset-db            # Drop and recreate all tables (destructive)
flask --app app.main seed-pitch-types    # Populate the pitch_types lookup table

# Schools
flask --app app.main create-school-func NAME SLUG PRIMARY SECONDARY TERTIARY ACCENT LIGHT DARK
flask --app app.main list-schools

# Users
flask --app app.main create-user-func EMAIL PASSWORD [--first-name X] [--last-name Y] [--school-id N] [--role admin|member]
flask --app app.main list-users
```

### Deployment

Deployed on Railway. `DATABASE_URL` is provided by Railway and rewritten from `postgres://` to `postgresql://` at startup; SSL is provisioned automatically; `gunicorn` serves in production.

**A persistent volume must be mounted at `/app/app/storage`.** Branding, logos, player photos, and the archived game files that power date-ranged hitting reports all live there. `entrypoint.sh` seeds defaults into the volume on first boot without overwriting existing files. Without a volume, uploaded assets and the game archive are lost on every deploy.

---

## Required Data Format

Standard TrackMan game exports in `.csv`, `.xlsx`, or `.xls`. Pitcher reports require:

| Column | Description |
|---|---|
| `Pitcher`, `PitcherId` | Pitcher name and identifier |
| `PitcherTeam` | Team ID, matched against the school's `trackman_id` |
| `TaggedPitchType` | Pitch type label |
| `PlateLocHeight`, `PlateLocSide` | Plate location |
| `BatterSide` | `Left` or `Right` |
| `RelSpeed`, `SpinRate`, `InducedVertBreak`, `HorzBreak` | Velocity and movement |
| `VertApprAngle`, `HorzApprAngle`, `RelHeight`, `RelSide`, `Extension`, `Tilt` | Release and approach |

Hitting reports additionally use `Batter`, `BatterId`, `PitcherThrows`, `PlayResult`, `KorBB`, and the batted-ball fields `ExitSpeed`, `Angle`, `Bearing`, and `Distance`. TrackMan populates these on balls in play; rows without them are treated as non-batted-ball events.

---

## School Branding

Branding lives in `app/storage/schools/{slug}/assets/branding.json` and is normally set through the subscription page rather than edited by hand.

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
    "logos": { "primary": "assets/logo.png" },
    "typography": { "font_family": "Graduate, sans-serif" },
    "report_settings": {
        "header_height_px": 120,
        "show_logo": true,
        "footer_text": "© 2026 School Name. All rights reserved."
    }
}
```

Logos load from `assets/logo.png`; player photos from `assets/players/{trackman_id}/pfp.png`.

---

## File Structure

```
pitcher_reports/
├── app/
│   ├── main.py                     # App factory, blueprint registration, storage routes
│   ├── cli.py                      # Flask CLI commands
│   ├── db/
│   │   ├── models.py               # School, User, Pitcher, Outing, Pitch_Types, Outing_Pitch_Stat
│   │   └── session.py
│   ├── routes/
│   │   ├── auth.py                 # Login, registration, school signup
│   │   ├── pages.py                # Dashboard, team overview, Excel exports
│   │   ├── upload.py               # Game upload, pitcher reports, save game
│   │   ├── batting.py              # Date-ranged hitting reports and PDF export
│   │   ├── account.py              # Account settings
│   │   ├── subscription.py         # Billing, branding, roster, player photos
│   │   ├── payments.py             # Stripe checkout + webhooks
│   │   └── utils.py                # Shared storage-path and toast helpers
│   ├── services/
│   │   ├── auth.py
│   │   ├── branding_loader.py
│   │   ├── file_validator.py
│   │   ├── report.py               # Pitcher stats + heat/break maps
│   │   ├── hitter_report.py        # Hitter stats + spray charts
│   │   ├── report_theme.py         # Shared plot theme, colors, strike zone
│   │   ├── game_archive.py         # Per-school raw game archive + manifest
│   │   ├── team_stats.py           # Database persistence for saved games
│   │   └── report_lab_generator.py # ReportLab PDF generation
│   ├── static/
│   ├── storage/
│   │   └── schools/{slug}/
│   │       ├── assets/             # branding.json, logo, roster, player photos
│   │       ├── temp/               # Generated charts (per-user)
│   │       ├── games/              # Archived game files + index.json manifest
│   │       └── reports/            # Generated PDFs (per-user)
│   └── templates/
├── migrations/                     # Alembic migration files
├── tests/
├── requirements.txt
└── README.md
```

---

## License

This project is source-available for non-commercial use only. Commercial licensing available upon request.

University logos, seals, and trademarks are the property of their respective institutions and are not licensed for reuse or redistribution.

## Contact

Thomas Eubank — [thomas.eubank516@gmail.com](mailto:thomas.eubank516@gmail.com)

Project Link: [https://github.com/WarmFreezer/pitcher_reports](https://github.com/WarmFreezer/pitcher_reports)

Live Site: [https://stat-line.app](https://stat-line.app)
