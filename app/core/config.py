from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_postgres_connection: str = ""
    cloudinary_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    
    supabase_url: str = ""
    supabase_anon_key: str = ""
    
    ig_username: str = ""
    ig_password: str = ""
    ig_session_file: str = "ig_session.json"

    class Config:
        env_file = ".env"
        # Allow extra fields in case .env has other undocumented variables
        extra = "ignore"

settings = Settings()
