# Baseball Pitcher Report Generator

A Flask-based web application that generates comprehensive pitcher performance reports from TrackMan baseball data files. Features multi-school support with custom branding, user authentication, and PDF report generation.

## Features

- 🔐 **User Authentication**: Secure login system with role-based access
- 🏫 **Multi-School Support**: Manage multiple schools with custom branding
- 📊 **Interactive Heat Maps**: Visualize pitch locations by batter handedness
- 📈 **Statistical Tables**: Detailed performance metrics for each pitcher
- 📄 **PDF Export**: Download individual or merged PDF reports
- 🎨 **Custom Branding**: School-specific colors, logos, and styling
- ⚡ **Batch Processing**: Process multiple pitchers from a single upload

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

## Installation

### 1. Clone or Download the Repository
```bash
git clone https://github.com/WarmFreezer/pitcher_reports.git
cd pitcher_reports
```

### 2. Create a Virtual Environment (Recommended)

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Required Packages
```bash
pip install -r requirements.txt
```

### 4. Initialize the Database
```bash
flask --app app.main init-db
```

### 5. Create a School

Before creating users, you need at least one school:

```bash
flask --app app.main create-school "School Name" school_slug --primary-color "#0033A0" --secondary-color "#FFCF00"
```

Example:
```bash
flask --app app.main create-school "Morehead State University" msu --primary-color "#0033A0" --secondary-color "#FFCF00"
```

**After creating a school, add a logo:**
1. Place your school logo at: `app/storage/schools/school_slug/assets/logo.png`
2. Update `app/storage/schools/school_slug/assets/branding.json` with additional branding settings

### 6. Create a User

```bash
flask --app app.main create-user EMAIL PASSWORD --first-name "First" --last-name "Last" --school-id 1 --role admin
```

Example:
```bash
flask --app app.main create-user coach@example.com password123 --first-name "John" --last-name "Doe" --school-id 1 --role admin
```

**To find your school ID:**
```bash
flask --app app.main list-schools
```

## Usage

### 1. Start the Application
```bash
flask --app app.main run
```

Or using Python:
```bash
python -m flask --app app.main run
```

### 2. Open in Browser

Navigate to: `http://127.0.0.1:5000`

### 3. Login

Use the credentials you created during setup.

### 4. Upload Data File

1. Click the **"Upload File"** button
2. Select an Excel file (.xlsx) containing TrackMan pitcher data
3. Wait for processing to complete

### 5. View and Download Reports

- **View Online**: Reports appear automatically after upload
- **Download Individual PDFs**: Click the "Download PDF" button on each report
- **Download All**: Use File → Download in the navbar to get all reports in one PDF

## School Branding Configuration

Each school's branding is stored in `app/storage/schools/{slug}/assets/branding.json`:

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
        "font_family": "Graduate, sans-serif",
        "font_weights": {
            "light": 300,
            "regular": 400,
            "bold": 700
        }
    },
    "report_settings": {
        "header_height_px": 120,
        "show_logo": true,
        "footer_text": "© 2024 School Name. All rights reserved."
    }
}
```

## CLI Commands

### Database
```bash
flask --app app.main init-db              # Initialize database
```

### Schools
```bash
flask --app app.main create-school NAME SLUG [OPTIONS]
flask --app app.main list-schools         # List all schools
```

### Users
```bash
flask --app app.main create-user EMAIL PASSWORD [OPTIONS]
flask --app app.main list-users           # List all users
```

## Required Data Format

The application accepts TrackMan baseball reports in Excel format (.xlsx). The file must include the following columns:

- `Pitcher` - Pitcher name
- `PitcherId` - Unique pitcher identifier
- `TaggedPitchType` - Type of pitch thrown
- `PlateLocHeight` - Vertical plate location
- `PlateLocSide` - Horizontal plate location
- `BatterSide` - Left/Right handed batter
- Additional TrackMan metrics

## Troubleshooting

### Port Already in Use

Change the port when starting the application:
```bash
flask --app app.main run --port 5001
```

### Module Not Found Errors

Ensure you're in the virtual environment and packages are installed:
```bash
pip install --upgrade -r requirements.txt
```

### Database Errors

If you encounter database issues, reinitialize:
```bash
flask --app app.main init-db
```

### Images Not Loading

Verify the absolute path configuration in `app/main.py` line 27:
```python
STORAGE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storage')
```

## File Structure

```
pitcher_reports/
├── app/
│   ├── __init__.py
│   ├── main.py              # Flask application
│   ├── cli.py               # CLI commands
│   ├── db/
│   │   ├── models.py        # Database models
│   │   └── session.py
│   ├── services/
│   │   ├── auth.py          # Authentication
│   │   ├── branding_loader.py
│   │   ├── file_validator.py
│   │   ├── pdf_generator.py
│   │   └── report.py        # Report generation
│   ├── static/
│   │   ├── scripts.js
│   │   ├── style.css
│   │   └── resources/
│   ├── storage/
│   │   └── schools/
│   │       └── {slug}/
│   │           ├── assets/
│   │           │   ├── logo.png
│   │           │   └── branding.json
│   │           ├── players/
│   │           ├── reports/
│   │           └── temp/
│   └── templates/
│       ├── dashboard.html
│       ├── index.html
│       └── login.html
├── instance/
│   └── pitcher_reports.db   # SQLite database
├── requirements.txt
└── README.md
```

## Dependencies

- **Flask** - Web framework
- **Flask-CORS** - Cross-origin resource sharing
- **Flask-Login** - User session management
- **Flask-Bcrypt** - Password hashing
- **Flask-SQLAlchemy** - Database ORM
- **pandas** - Data manipulation
- **openpyxl** - Excel file support
- **matplotlib** - Plotting library
- **seaborn** - Statistical visualization
- **xhtml2pdf** - HTML to PDF conversion
- **PyPDF2** - PDF manipulation
- **python-magic-bin** - File type detection

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is source-available for non-commercial use only.
Commercial licensing is available upon request.

University logos, seals, and trademarks are the property of their respective institutions and are not licensed for reuse or redistribution.

## Contact

Thomas Eubank - [thomas.eubank516@gmail.com](mailto:thomas.eubank516@gmail.com)

Project Link: [https://github.com/WarmFreezer/pitcher_reports](https://github.com/WarmFreezer/pitcher_reports)

## Acknowledgments

- MSU Baseball Analytics Team
- Prof. Asim Chaudhry

---

**Last Updated:** February 2026