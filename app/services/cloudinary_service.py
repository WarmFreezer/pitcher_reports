from dotenv import load_dotenv
import os
from pathlib import Path
import cloudinary as cd
import cloudinary.api as capi
import requests
import cloudinary.uploader as cu
from cloudinary.utils import cloudinary_url as cd_url

env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
print("Cloudinary Cloud Name:", os.environ.get('CLOUDINARY_CLOUD_NAME'))

class CloudinaryService:
    cd.config(
        cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key = os.environ.get('CLOUDINARY_API_KEY'),
        api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
        secure = True
    )

    @staticmethod
    def upload_image(folder, file_path, public_id):
        try:
            upload_result = cu.upload(file_path, public_id=public_id, folder=folder)
            print(f"✓ Upload successful: {upload_result.get('secure_url')}")
            return upload_result
        except Exception as e:
            print(f"✗ Upload failed: {str(e)}")
            raise

    @staticmethod
    def get_image_url(public_id, ext='jpg'):
        cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
        return f"https://res.cloudinary.com/{cloud_name}/image/upload/{public_id}.{ext}"
    
    @staticmethod
    def img_exists(public_id, extensions=None):
        if extensions is None:
            extensions = ['png', 'jpg', 'jpeg', 'gif']

        cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
        for ext in extensions:
            url = f"https://res.cloudinary.com/{cloud_name}/image/upload/{public_id}.{ext}"
            try:
                # HEAD request is faster than GET - just checks if URL exists
                response = requests.head(url, timeout=5)
                if response.status_code == 200:
                    return url
            except requests.RequestException:
                continue
        
        return None