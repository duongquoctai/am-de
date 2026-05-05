from supabase import create_client, Client
from app.core.config import settings

class SupabaseService:
    def __init__(self):
        self.supabase: Client | None = None
        if settings.supabase_url and settings.supabase_anon_key:
            self.supabase = create_client(settings.supabase_url, settings.supabase_anon_key)

    def create_job(self, keyword: str, platform: str, target_count: int) -> str:
        if not self.supabase:
            print("Warning: Supabase client not initialized")
            return "dummy-job-id"
        response = self.supabase.table("crawl_jobs").insert({
            "keyword": keyword,
            "platform": platform,
            "target_count": target_count,
            "status": "pending"
        }).execute()
        return response.data[0]["id"]

    def update_job_status(self, job_id: str, status: str, saved_count: int = None, found_count: int = None, error_message: str = None):
        if not self.supabase:
            return
        
        payload = {"status": status}
        if saved_count is not None:
            payload["saved_count"] = saved_count
        if found_count is not None:
            payload["found_count"] = found_count
        if error_message is not None:
            payload["error_message"] = error_message
            
        self.supabase.table("crawl_jobs").update(payload).eq("id", job_id).execute()

    def insert_video(self, video_data: dict):
        if not self.supabase:
            return
        # Using on_conflict for the unique index defined in schema
        self.supabase.table("videos").upsert(video_data, on_conflict="platform,source_id").execute()

supabase_service = SupabaseService()
