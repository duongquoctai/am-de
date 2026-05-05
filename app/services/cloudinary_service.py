import cloudinary
import cloudinary.uploader
from app.core.config import settings
import os

# Initialize Cloudinary if credentials are provided
if settings.cloudinary_name and settings.cloudinary_api_key and settings.cloudinary_api_secret:
    cloudinary.config( 
        cloud_name=settings.cloudinary_name, 
        api_key=settings.cloudinary_api_key, 
        api_secret=settings.cloudinary_api_secret 
    )

class CloudinaryService:
    @staticmethod
    def upload_video(file_path: str, public_id_prefix: str = "am_de_videos/") -> str:
        """
        Uploads a video to Cloudinary.
        Returns the secure storage URL.
        """
        response = cloudinary.uploader.upload(
            file_path, 
            resource_type="video",
            folder=public_id_prefix
        )
        return response.get("secure_url")

    @staticmethod
    def delete_local_file(file_path: str):
        """
        Deletes the temporary local file.
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file {file_path}: {str(e)}")

cloudinary_service = CloudinaryService()
