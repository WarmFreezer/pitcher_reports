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
            return None
        
        try:
            with open(branding_path, 'r') as f:
                branding_data = json.load(f)
            return branding_data
        except Exception as e:
            print(f"Error loading branding for {school_slug}: {e}")
            return {
                'name': 'Unknown School',
                "primary": "#0033A0",
                "secondary": "#FFCF00",
                "tertiary": "#001D39",
                "dark": "#343434",
                "light": "#ECECEC",
                "accent": "#005EB8",
                'logo': None
            }
        
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
            raise FileNotFoundError(f"Branding file not found for school: {school_slug}")

        with open(branding_path, 'w') as f:
            json.dump(branding_data, f, indent=4)

        return True