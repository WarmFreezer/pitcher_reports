import json
import os
import re
from pathlib import Path
from typing import Any

from app.db.models import db, School

class BrandingLoader:
    """Reads/writes each school's branding.json and locates its logo on disk, keyed by school id."""

    # Resolved at import time relative to this file so it works regardless of cwd
    SCHOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'storage', 'schools')

    @staticmethod
    def _with_live_school_name(school_id: int, branding: dict[str, Any]) -> dict[str, Any]:
        """
        Overrides branding['school']['name'] with the school's actual name from the
        schools table, so a branding.json/default.json placeholder (or another
        school's leftover name) never gets shown in place of this tenant's own name --
        e.g. in the default footer_text template (see default.json).
        """
        school = db.session.get(School, school_id)
        if school is not None:
            branding.setdefault('school', {})['name'] = school.name
        return branding

    @staticmethod
    def get_branding(school_id: int) -> dict[str, Any]:
        """Load a school's branding.json, falling back to default.json if missing or corrupt."""
        branding_path = os.path.join(BrandingLoader.SCHOOLS, str(school_id), 'assets', 'branding.json')
        if not os.path.exists(branding_path):
            print(f"Branding file not found for school: {school_id}")
            with open(os.path.join(BrandingLoader.SCHOOLS, 'default.json'), 'r', encoding='utf-8') as f:
                return BrandingLoader._with_live_school_name(school_id, json.load(f))
        try:
            with open(branding_path, 'r', encoding='utf-8') as f:
                return BrandingLoader._with_live_school_name(school_id, json.load(f))
        except Exception as e:
            # Fall back to defaults so the app stays usable even with a corrupt branding file
            print(f"Error loading branding for {school_id}: {e}")
            with open(os.path.join(BrandingLoader.SCHOOLS, 'default.json'), 'r', encoding='utf-8') as f:
                return BrandingLoader._with_live_school_name(school_id, json.load(f))

    @staticmethod
    def get_logo_path(school_id: int) -> str | None:
        """Public URL of the school's logo, checking png/jpg/jpeg/svg in priority order."""
        # Check extensions in priority order — PNG preferred, SVG last
        logo_dir = os.path.join(BrandingLoader.SCHOOLS, str(school_id), 'assets')
        for ext in ['png', 'jpg', 'jpeg', 'svg']:
            logo_path = os.path.join(logo_dir, f'logo.{ext}')
            if os.path.exists(logo_path):
                return f'/storage/schools/{school_id}/assets/logo.{ext}'
        return None

    @staticmethod
    def create_school_dir(school_id: int, branding_data: dict[str, Any]) -> str:
        """Create a new school's storage directory and write its initial branding.json."""
        school_dir = os.path.join(BrandingLoader.SCHOOLS, str(school_id))
        Path(school_dir).mkdir(parents=True, exist_ok=True)

        assets_dir = os.path.join(school_dir, 'assets')
        Path(assets_dir).mkdir(parents=True, exist_ok=True)

        branding_path = os.path.join(assets_dir, 'branding.json')
        with open(branding_path, 'w') as f:
            json.dump(branding_data, f, indent=4)

        return branding_path

    @staticmethod
    def update_branding(school_id: int, branding_data: dict[str, Any]) -> bool:
        """Overwrite a school's branding.json, creating its directory if needed."""
        branding_path = os.path.join(BrandingLoader.SCHOOLS, str(school_id), 'assets', 'branding.json')
        # Create the directory if it doesn't exist yet (e.g. newly provisioned school)
        os.makedirs(os.path.dirname(branding_path), exist_ok=True)
        with open(branding_path, 'w') as f:
            json.dump(branding_data, f, indent=4)
        return True

    @staticmethod
    def get_default_branding() -> dict[str, Any]:
        """Load the global default.json used as a branding fallback for schools without their own branding.json."""
        with open(os.path.join(BrandingLoader.SCHOOLS, 'default.json'), 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def update_default_colors(colors: dict[str, str]) -> None:
        """Merge new color tokens into default.json's colors block."""
        default_path = os.path.join(BrandingLoader.SCHOOLS, 'default.json')
        with open(default_path, 'r', encoding='utf-8') as f:
            default_data = json.load(f)
        default_data['colors'].update(colors)
        with open(default_path, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, indent=4)

    @staticmethod
    def validate_colors(colors: dict[str, Any]) -> str | None:
        """Check that the four required color tokens are present and valid hex; returns an error message, or None if valid."""
        required = {'primary', 'secondary', 'tertiary', 'accent'}
        if not required.issubset(colors.keys()):
            return 'Missing required color tokens.'
        hex_re = re.compile(r'^#[0-9a-fA-F]{6}$')
        for token, value in colors.items():
            if not hex_re.match(value):
                return f'Invalid hex color for {token}: {value}'
        return None

    @staticmethod
    def is_dark(color_hex: str) -> bool:
        """Whether a hex color's perceived brightness (W3C formula) reads as dark."""
        # W3C perceived brightness formula — values below 128 are considered dark
        color_hex = color_hex.lstrip('#')
        r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        return brightness < 128
