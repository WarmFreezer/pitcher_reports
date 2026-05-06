import json
import os
from pathlib import Path

class BrandingLoader:
    SCHOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'storage', 'schools')

    @staticmethod
    def get_branding(school_slug):
        branding_path = os.path.join(BrandingLoader.SCHOOLS, school_slug, 'assets', 'branding.json')
        if not os.path.exists(branding_path):
            print(f"Branding file not found for school: {school_slug}")
            return json.load(open(os.path.join(BrandingLoader.SCHOOLS, 'default.json'), 'r'))
        try:
            with open(branding_path, 'r') as f:
                branding_data = json.load(f)
            return branding_data
        except Exception as e:
            print(f"Error loading branding for {school_slug}: {e}")
            return json.load(open(os.path.join(BrandingLoader.SCHOOLS, 'default.json'), 'r'))
        
    @staticmethod
    def get_logo_path(school_slug):
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
        if not os.path.exists(branding_path):
            os.makedirs(os.path.dirname(branding_path), exist_ok=True)
            with open(branding_path, 'w') as f:
                json.dump(branding_data, f, indent=4)
        else:
            with open(branding_path, 'w') as f:
                json.dump(branding_data, f, indent=4)

        return True

    @staticmethod
    def is_dark(color_hex):
        color_hex = color_hex.lstrip('#')
        r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        return brightness < 128