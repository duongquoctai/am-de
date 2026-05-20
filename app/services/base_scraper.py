import os
import uuid
import httpx
import logging
from typing import AsyncGenerator, Dict, Any, List
from app.services.cloudinary_service import cloudinary_service
from app.services.supabase_service import supabase_service
from app.core.config import settings

logger = logging.getLogger(__name__)

class BaseScraper:
    def __init__(self):
        pass

    def _get_existing_source_ids(self, platform: str) -> set:
        """
        Fetch existing source_ids from Supabase for the given platform to perform central in-memory deduplication.
        """
        if not supabase_service.supabase:
            logger.warning("Supabase client not initialized. Returning empty set.")
            return set()
        try:
            response = supabase_service.supabase.table("videos").select("source_id").eq("platform", platform).execute()
            if hasattr(response, "data") and response.data:
                return {str(item["source_id"]) for item in response.data if "source_id" in item}
            return set()
        except Exception as e:
            logger.error(f"Error fetching existing source IDs for {platform}: {e}")
            return set()

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
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.tiktok.com/" if platform == "tiktok" else "https://www.douyin.com/" if platform == "douyin" else "https://www.instagram.com/",
                "Accept": "*/*"
            }
            if platform == "tiktok" and getattr(settings, "tiktok_cookie", None):
                headers["Cookie"] = settings.tiktok_cookie
            elif platform == "douyin" and getattr(settings, "douyin_cookie", None):
                headers["Cookie"] = settings.douyin_cookie
                
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=60.0) as client:
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
        if crawl_type == "hashtag":
            fetcher = getattr(self, "_fetch_from_hashtag", None) or getattr(self, "_fetch_from_keyword", None)
        elif crawl_type == "keyword":
            fetcher = getattr(self, "_fetch_from_keyword", None) or getattr(self, "_fetch_from_hashtag", None)
        else:
            fetcher = getattr(self, "_fetch_from_profile", None)

        if not fetcher:
            error_msg = f"Fetcher for {crawl_type} not implemented in {self.__class__.__name__}"
            logger.error(error_msg)
            supabase_service.update_job_status(job_id, status="failed", error_message=error_msg)
            return

        # 1. Fetch existing IDs ONCE before the loop starts
        existing_ids = self._get_existing_source_ids(platform)
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
                    source_id = str(item.get("source_id")) if item.get("source_id") is not None else None
                    if not source_id:
                        continue
                    
                    # 3. FAST IN-MEMORY CHECK
                    if source_id in existing_ids:
                        logger.info(f"[*] Skipping duplicate video: {source_id}")
                        
                        # SMART EARLY EXIT
                        if crawl_type == "profile":
                            logger.info("[*] Reached already-scraped history for profile. Stopping early.")
                            break
                        
                        continue

                    # 4. Only process NEW videos
                    success = await self.process_video_item(job_id, platform, item)
                    if success:
                        saved_count += 1
                        existing_ids.add(source_id)  # Update local cache
                        supabase_service.update_job_status(job_id, status="processing", saved_count=saved_count)
                    
                    if saved_count >= limit:
                        break
            else:
                for item in results:
                    source_id = str(item.get("source_id")) if item.get("source_id") is not None else None
                    if not source_id:
                        continue
                    
                    # 3. FAST IN-MEMORY CHECK
                    if source_id in existing_ids:
                        logger.info(f"[*] Skipping duplicate video: {source_id}")
                        
                        # SMART EARLY EXIT
                        if crawl_type == "profile":
                            logger.info("[*] Reached already-scraped history for profile. Stopping early.")
                            break
                        
                        continue

                    # 4. Only process NEW videos
                    success = await self.process_video_item(job_id, platform, item)
                    if success:
                        saved_count += 1
                        existing_ids.add(source_id)  # Update local cache
                        supabase_service.update_job_status(job_id, status="processing", saved_count=saved_count)
                    
                    if saved_count >= limit:
                        break
            
            logger.info(f"--- [Job COMPLETED] Platform: {platform} | ID: {job_id} | Total Saved: {saved_count} ---")
            supabase_service.update_job_status(job_id, status="completed")
        except Exception as e:
            logger.error(f"--- [Job FAILED] Platform: {platform} | ID: {job_id} | Error: {str(e)} ---")
            supabase_service.update_job_status(job_id, status="failed", error_message=str(e))
