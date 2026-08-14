import os
from flask import current_app, session
from flask_login import current_user


def flash_toast(message: str, type: str = 'info') -> None:
    """Queue a toast notification, shown on the next page render then cleared."""
    toasts = session.get('_toasts', [])
    toasts.append({'message': message, 'type': type})
    session['_toasts'] = toasts


def get_school_directories() -> tuple[str, str]:
    """Return (temp_dir, reports_dir) for the current user's school, creating them if needed."""
    if not current_user.is_authenticated:
        raise Exception("User not authenticated")

    storage = current_app.config['STORAGE']

    school_temp_dir = os.path.join(storage, 'schools', str(current_user.school_id), 'temp')
    school_output_dir = os.path.join(storage, 'schools', str(current_user.school_id), 'reports')

    os.makedirs(school_temp_dir, exist_ok=True)
    os.makedirs(school_output_dir, exist_ok=True)

    return school_temp_dir, school_output_dir


def get_school_games_directory() -> str:
    """Return the archived-games dir for the current user's school, creating it if needed."""
    if not current_user.is_authenticated:
        raise Exception("User not authenticated")

    return get_games_directory(current_user.school_id)


def get_games_directory(school_id: int) -> str:
    """Return the archived-games dir for an explicit school id, creating it if needed."""
    games_dir = os.path.join(current_app.config['STORAGE'], 'schools', str(school_id), 'games')
    os.makedirs(games_dir, exist_ok=True)
    return games_dir
