import os
import uuid
import httpx
import logging
from typing import AsyncGenerator, Dict, Any, List
from app.services.cloudinary_service import cloudinary_service
from app.services.supabase_service import supabase_service

logger = logging.getLogger(__name__)

class BaseScraper:
    def __init__(self):
        pass

    async def process_video_item(self, job_id: str, platform: str, item: Dict[str, Any]) -> bool:
        """
        Standardized video processing: Download -> Upload to Cloudinary -> Save to Supabase
        
        Expected item format:
        {
            "video_url": "...",
            "source_id": "...",
            "source_url": "...",
            "author_username": "...",
            "original_caption": "...",
            "duration": 0,
            "thumbnail_url": "..." (optional)
        }
        """
        temp_file = f"{uuid.uuid4().hex}.mp4"
        video_url = item.get("video_url")
        source_id = item.get("source_id")
        
        if not video_url:
            logger.error(f"[Job {job_id}] No video URL found for item {source_id}")
            return False

        logger.info(f"[Job {job_id}] Processing {platform} item {source_id} by @{item.get('author_username')}")
        
        try:
            # 1. Download
            logger.info(f"[Job {job_id}] Downloading video from {video_url[:50]}...")
            async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                async with client.stream("GET", str(video_url)) as resp:
                    resp.raise_for_status()
                    with open(temp_file, 'wb') as f:
                        async for chunk in resp.aiter_bytes():
                            f.write(chunk)
            
            # 2. Upload to Cloudinary
            logger.info(f"[Job {job_id}] Uploading to Cloudinary...")
            storage_url = cloudinary_service.upload_video(temp_file, public_id_prefix=f"am_de_videos/{job_id}/")
            
            if not storage_url:
                logger.error(f"[Job {job_id}] Cloudinary upload failed for item {source_id}")
                return False

            # 3. Save to Supabase
            video_record = {
                "job_id": job_id,
                "keyword": item.get("original_caption", "unknown")[:255] if item.get("original_caption") else "unknown",
                "platform": platform,
                "source_id": source_id,
                "source_url": item.get("source_url"),
                "author_username": item.get("author_username"),
                "original_caption": item.get("original_caption", ""),
                "duration": item.get("duration", 0),
                "storage_url": storage_url,
                "thumbnail_url": item.get("thumbnail_url") or storage_url.replace(".mp4", ".jpeg"),
                "post_status": "idle"
            }
            
            supabase_service.insert_video(video_record)
            logger.info(f"[Job {job_id}] Record inserted into Supabase for {platform}:{source_id}")
            return True

        except Exception as e:
            logger.error(f"[Job {job_id}] Error processing {platform} video {source_id}: {e}")
            return False
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    async def execute_job(self, job_id: str, target: str, crawl_type: str, limit: int, platform: str):
        """
        Main orchestrator for crawling. Subclasses must implement _fetch_from_keyword and _fetch_from_profile.
        """
        logger.info(f"--- [Job START] Platform: {platform} | ID: {job_id} | Target: {target} | Type: {crawl_type} | Limit: {limit} ---")
        supabase_service.update_job_status(job_id, status="processing")
        
        # Determine fetcher method
        if crawl_type == "hashtag" or crawl_type == "keyword":
            fetcher = getattr(self, "_fetch_from_keyword", None) or getattr(self, "_fetch_from_hashtag", None)
        else:
            fetcher = getattr(self, "_fetch_from_profile", None)

        if not fetcher:
            error_msg = f"Fetcher for {crawl_type} not implemented in {self.__class__.__name__}"
            logger.error(error_msg)
            supabase_service.update_job_status(job_id, status="failed", error_message=error_msg)
            return

        saved_count = 0
        try:
            # fetcher should be a generator (sync or async)
            import inspect
            sig = inspect.signature(fetcher)
            if "platform" in sig.parameters:
                results = fetcher(target, limit, platform=platform)
            else:
                results = fetcher(target, limit)
            
            # Support both sync and async generators
            if hasattr(results, "__aiter__"):
                async for item in results:
                    if await self._process_and_update(job_id, platform, item, saved_count):
                        saved_count += 1
            else:
                for item in results:
                    if await self._process_and_update(job_id, platform, item, saved_count):
                        saved_count += 1
            
            logger.info(f"--- [Job COMPLETED] Platform: {platform} | ID: {job_id} | Total Saved: {saved_count} ---")
            supabase_service.update_job_status(job_id, status="completed")
        except Exception as e:
            logger.error(f"--- [Job FAILED] Platform: {platform} | ID: {job_id} | Error: {str(e)} ---")
            supabase_service.update_job_status(job_id, status="failed", error_message=str(e))

    async def _process_and_update(self, job_id: str, platform: str, item: Dict[str, Any], saved_count: int) -> bool:
        success = await self.process_video_item(job_id, platform, item)
        if success:
            supabase_service.update_job_status(job_id, status="processing", saved_count=saved_count + 1)
        return success
