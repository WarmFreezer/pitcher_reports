import json
import os
from pathlib import Path


class BrandingLoader:
    # Resolved at import time relative to this file so it works regardless of cwd
    SCHOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'storage', 'schools')

    @staticmethod
    def get_branding(school_slug):
        branding_path = os.path.join(BrandingLoader.SCHOOLS, school_slug, 'assets', 'branding.json')
        if not os.path.exists(branding_path):
            print(f"Branding file not found for school: {school_slug}")
            return json.load(open(os.path.join(BrandingLoader.SCHOOLS, 'default.json'), 'r'))
        try:
            with open(branding_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            # Fall back to defaults so the app stays usable even with a corrupt branding file
            print(f"Error loading branding for {school_slug}: {e}")
            return json.load(open(os.path.join(BrandingLoader.SCHOOLS, 'default.json'), 'r'))

    @staticmethod
    def get_logo_path(school_slug):
        # Check extensions in priority order — PNG preferred, SVG last
        logo_dir = os.path.join(BrandingLoader.SCHOOLS, school_slug, 'assets')
        for ext in ['png', 'jpg', 'jpeg', 'svg']:
            logo_path = os.path.join(logo_dir, f'logo.{ext}')
            if os.path.exists(logo_path):
                return f'/storage/schools/{school_slug}/assets/logo.{ext}'
        return None

    @staticmethod
    def create_school_dir(school_slug, branding_data):
        school_dir = os.path.join(BrandingLoader.SCHOOLS, school_slug)
        Path(school_dir).mkdir(parents=True, exist_ok=True)

        assets_dir = os.path.join(school_dir, 'assets')
        Path(assets_dir).mkdir(parents=True, exist_ok=True)

        branding_path = os.path.join(assets_dir, 'branding.json')
        with open(branding_path, 'w') as f:
            json.dump(branding_data, f, indent=4)

        return branding_path

    @staticmethod
    def update_branding(school_slug, branding_data):
        branding_path = os.path.join(BrandingLoader.SCHOOLS, school_slug, 'assets', 'branding.json')
        # Create the directory if it doesn't exist yet (e.g. newly provisioned school)
        os.makedirs(os.path.dirname(branding_path), exist_ok=True)
        with open(branding_path, 'w') as f:
            json.dump(branding_data, f, indent=4)
        return True

    @staticmethod
    def is_dark(color_hex):
        # W3C perceived brightness formula — values below 128 are considered dark
        color_hex = color_hex.lstrip('#')
        r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        return brightness < 128
