import os
from flask import current_app
from flask_login import current_user


def get_school_directories():
    """Return (temp_dir, reports_dir) for the current user's school, creating them if needed."""
    if not current_user.is_authenticated:
        raise Exception("User not authenticated")

    school_slug = current_user.school.slug
    storage = current_app.config['STORAGE']

    school_temp_dir = os.path.join(storage, 'schools', school_slug, 'temp')
    school_output_dir = os.path.join(storage, 'schools', school_slug, 'reports')

    os.makedirs(school_temp_dir, exist_ok=True)
    os.makedirs(school_output_dir, exist_ok=True)

    return school_temp_dir, school_output_dir
