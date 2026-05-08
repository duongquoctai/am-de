import os
import uuid
import re
import httpx
import logging
import base64
import instaloader
from typing import AsyncGenerator, Tuple, Dict, Any, Iterator, Literal
from app.core.config import settings
from app.services.cloudinary_service import cloudinary_service
from app.services.supabase_service import supabase_service

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Force output to stdout
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False # avoid double logging if parent also captures it

class InstagramScraper:
    def __init__(self):
        self.L = instaloader.Instaloader()
        self.session_file = getattr(settings, "ig_session_file", "instaloader_session")
        self.username = getattr(settings, "ig_username", "")
        self.password = getattr(settings, "ig_password", "")
        self.is_initialized = False

    def _load_session(self):
        """
        Production-ready session management:
        Priority 1: Decode from Base64 ENV (ig_session_base64)
        Priority 2: Load from local file (ig_session_file)
        """
        if self.is_initialized:
            return

        # PRIORITY 1: PRODUCTION MODE (Load from Base64 settings/ENV)
        session_b64 = getattr(settings, "ig_session_base64", None)
        if session_b64:
            logger.info("[*] Production Mode: Decoding session from Base64 settings...")
            try:
                decoded_data = base64.b64decode(session_b64)
                with open(self.session_file, "wb") as f:
                    f.write(decoded_data)
                
                self.L.load_session_from_file(self.username, filename=self.session_file)
                logger.info("[+] Successfully loaded session from Base64 settings.")
                self.is_initialized = True
                return
            except Exception as e:
                logger.error(f"[-] Critical: Invalid Base64 Session in Production: {e}")
                raise RuntimeError(f"CRITICAL: Invalid Base64 Session. Scraper aborted to protect IP: {e}")

        # PRIORITY 2: LOCAL DEV MODE (Load from existing local file)
        if os.path.exists(self.session_file):
            logger.info(f"[*] Local Mode: Loading session from {self.session_file}...")
            try:
                self.L.load_session_from_file(self.username, filename=self.session_file)
                logger.info(f"[+] Successfully loaded local session from {self.session_file}.")
                self.is_initialized = True
                return
            except Exception as e:
                logger.error(f"[-] Local session failed: {e}")

        # PRIORITY 3: FALLBACK (Highly discouraged - blocked to prevent bans)
        logger.error("No session file or Base64 settings found. Scraper aborted.")
        raise FileNotFoundError("CRITICAL: No valid Instagram session provided. Please set IG_SESSION_BASE64 or provide a local session file.")

    def _fetch_from_hashtag(self, hashtag_name: str, limit: int) -> Iterator[instaloader.Post]:
        """
        Robust generator for hashtag posts that handles recent IG structural changes.
        """
        self._load_session()
        hashtag_clean = re.sub(r'[^a-zA-Z0-9]', '', hashtag_name).lower()
        logger.info(f"[Hashtag Fetcher] Initializing for #{hashtag_clean} (Limit: {limit})")
        hashtag_obj = instaloader.Hashtag.from_name(self.L.context, hashtag_clean)
        
        count = 0
        # Try standard get_top_posts first
        try:
            for post in hashtag_obj.get_top_posts():
                if count >= limit: return
                if post.is_video:
                    yield post
                    count += 1
        except (KeyError, StopIteration, Exception) as e:
            logger.warning(f"Standard get_top_posts failed ({e}), attempting robust section parsing...")

        # Robust Fallback: Manually parse sections if the library fails
        if count < limit:
            try:
                hashtag_obj._obtain_metadata()
                for section_type in ["top", "recent"]:
                    data = hashtag_obj._metadata(section_type)
                    if not data or "sections" not in data: continue
                    
                    for section in data["sections"]:
                        lc = section.get("layout_content", {})
                        items = []
                        if "fill_items" in lc: items.extend(lc["fill_items"])
                        if "medias" in lc: items.extend(lc["medias"])
                        if "one_by_two_item" in lc: items.append(lc["one_by_two_item"])
                        
                        for item in items:
                            if count >= limit: return
                            if not item: continue
                            
                            # Media extraction helper logic
                            m = item.get("media") or item.get("clips") or item
                            if isinstance(m, dict) and "clips" in m:
                                m = m["clips"].get("media", m["clips"])
                            
                            if isinstance(m, dict) and (m.get("is_video") or m.get("video_duration")):
                                logger.info(f"[Robust Fetch] Found video/reel: {m.get('code')}")
                                post = instaloader.Post.from_iphone_struct(self.L.context, m)
                                yield post
                                count += 1
            except Exception as e:
                logger.error(f"Robust hashtag fetch failed completely: {e}")

    def _fetch_from_profile(self, username: str, limit: int) -> Iterator[instaloader.Post]:
        """
        Generator for profile Reels.
        """
        self._load_session()
        username_clean = username.strip().replace("@", "").lower()
        logger.info(f"[Profile Fetcher] Initializing for @{username_clean} (Limit: {limit})")
        profile = instaloader.Profile.from_name(self.L.context, username_clean)
        
        count = 0
        for post in profile.get_reels():
            if count >= limit: break
            yield post
            count += 1

    async def process_video_item(self, job_id: str, post: instaloader.Post) -> bool:
        """
        Atomic unit: Metadata -> Download -> Cloudinary -> Supabase
        """
        temp_file = f"{uuid.uuid4().hex}.mp4"
        logger.info(f"[Job {job_id}] Processing post {post.shortcode} by @{post.owner_username}")
        try:
            metadata = {
                "source_id": str(post.shortcode),
                "source_url": f"https://www.instagram.com/p/{post.shortcode}/",
                "author_username": post.owner_username,
                "original_caption": post.caption if post.caption else "",
                "duration": int(post.video_duration) if post.video_duration else 0
            }

            logger.info(f"[Job {job_id}] Downloading video from {post.video_url[:50]}...")
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", str(post.video_url)) as resp:
                    resp.raise_for_status()
                    with open(temp_file, 'wb') as f:
                        async for chunk in resp.aiter_bytes():
                            f.write(chunk)
            
            logger.info(f"[Job {job_id}] Uploading to Cloudinary...")
            storage_url = cloudinary_service.upload_video(temp_file, public_id_prefix=f"am_de_videos/{job_id}/")
            
            if storage_url:
                video_record = {
                    "job_id": job_id,
                    "keyword": post.caption[:255] if post.caption else "unknown",
                    "platform": "instagram",
                    "source_id": metadata["source_id"],
                    "source_url": metadata["source_url"],
                    "author_username": metadata["author_username"],
                    "original_caption": metadata["original_caption"],
                    "duration": metadata["duration"],
                    "storage_url": storage_url,
                    "post_status": "idle"
                }
                supabase_service.insert_video(video_record)
                logger.info(f"[Job {job_id}] Record inserted into Supabase.")
                return True
            return False
        except Exception as e:
            logger.error(f"[Job {job_id}] Error processing video {post.shortcode}: {e}")
            return False
        finally:
            if os.path.exists(temp_file): os.remove(temp_file)

    async def execute_job(self, job_id: str, target: str, crawl_type: str, limit: int):
        """
        Main orchestrator called by BackgroundTasks.
        """
        logger.info(f"--- [Job START] ID: {job_id} | Target: {target} | Type: {crawl_type} | Limit: {limit} ---")
        supabase_service.update_job_status(job_id, status="processing")
        
        fetcher = self._fetch_from_hashtag if crawl_type == "hashtag" else self._fetch_from_profile
        
        saved_count = 0
        try:
            for post in fetcher(target, limit):
                logger.info(f"[Job {job_id}] Found candidate post: {post.shortcode}")
                success = await self.process_video_item(job_id, post)
                if success:
                    saved_count += 1
                    supabase_service.update_job_status(job_id, status="processing", saved_count=saved_count)
            
            logger.info(f"--- [Job COMPLETED] ID: {job_id} | Total Saved: {saved_count} ---")
            supabase_service.update_job_status(job_id, status="completed")
        except Exception as e:
            logger.error(f"--- [Job FAILED] ID: {job_id} | Error: {e} ---")
            supabase_service.update_job_status(job_id, status="failed", error_message=str(e))

instagram_scraper = InstagramScraper()
