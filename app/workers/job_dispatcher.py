import os
from tempfile import TemporaryDirectory
from app.services.instagrapi_service import instagrapi_service
from app.services.cloudinary_service import cloudinary_service
from app.services.supabase_service import supabase_service

from instagrapi.exceptions import (
    ChallengeRequired,
    FeedbackRequired,
    PleaseWaitFewMinutes,
    ClientThrottledError,
    LoginRequired
)

async def process_crawl_job(job_id: str, keyword: str, platform: str, target_count: int):
    """
    Asynchronous adapter to coordinate Instagrapi Scraper with Cloudinary and Supabase.
    """
    supabase_service.update_job_status(job_id, status="processing")
    
    saved_count = 0
    found_count = 0
    
    with TemporaryDirectory() as temp_dir:
        try:
            if platform.lower() == "instagram":
                
                async for file_path, metadata in instagrapi_service.get_top_media(keyword, target_count, temp_dir):
                    found_count += 1
                    supabase_service.update_job_status(job_id, status="processing", found_count=found_count)
                    
                    try:
                        storage_url = cloudinary_service.upload_video(file_path, public_id_prefix=f"am_de_videos/{job_id}/")
                        
                        if storage_url:
                            video_record = {
                                "job_id": job_id,
                                "keyword": keyword,
                                "platform": "instagram",
                                "source_id": metadata["source_id"],
                                "source_url": metadata["source_url"],
                                "author_username": metadata["author_username"],
                                "original_caption": metadata["original_caption"],
                                "duration": metadata.get("duration"),
                                "storage_url": storage_url,
                                "post_status": "idle"
                            }
                            supabase_service.insert_video(video_record)
                            
                            saved_count += 1
                            supabase_service.update_job_status(job_id, status="processing", saved_count=saved_count)
                            
                    except Exception as loop_err:
                        print(f"Error handling video {metadata['source_id']}: {loop_err}")
                    finally:
                        cloudinary_service.delete_local_file(file_path)
            else:
                raise ValueError(f"Platform '{platform}' is not implemented yet.")
                
            supabase_service.update_job_status(job_id, status="completed")
            
        except Exception as e:
            # Explicitly decode complex Instagrapi limitations and capture strings elegantly
            error_details = str(e)
            if isinstance(e, ChallengeRequired):
                error_details = f"BLOCK | Challenge/2FA verification dynamically requested: {e}"
            elif isinstance(e, FeedbackRequired):
                error_details = f"BLOCK | FeedbackRequired issued indicating abusive pattern block: {e}"
            elif isinstance(e, PleaseWaitFewMinutes):
                error_details = f"THROTTLE | PleaseWaitFewMinutes invoked. Massive rate limit. {e}"
            elif isinstance(e, ClientThrottledError):
                error_details = f"THROTTLE | ClientThrottledError (HTTP 429) hit aggressively. {e}"
            elif isinstance(e, LoginRequired):
                error_details = f"EXCEPTION | Login connection rejected mapping cleanly: {e}"
                
            supabase_service.update_job_status(job_id, status="failed", error_message=error_details)
