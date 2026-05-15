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

from app.services.base_scraper import BaseScraper

class InstagramScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.L = instaloader.Instaloader()
        self.session_file = getattr(settings, "ig_session_file", "instaloader_session")
        self.username = getattr(settings, "ig_username", "")
        self.password = getattr(settings, "ig_password", "")
        self.is_initialized = False

    def _load_session(self):
        """
        Production-ready session management.
        """
        if self.is_initialized:
            return

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
                raise RuntimeError(f"CRITICAL: Invalid Base64 Session: {e}")

        if os.path.exists(self.session_file):
            logger.info(f"[*] Local Mode: Loading session from {self.session_file}...")
            try:
                self.L.load_session_from_file(self.username, filename=self.session_file)
                logger.info(f"[+] Successfully loaded local session.")
                self.is_initialized = True
                return
            except Exception as e:
                logger.error(f"[-] Local session failed: {e}")

        raise FileNotFoundError("CRITICAL: No valid Instagram session provided.")

    def _fetch_from_hashtag(self, hashtag_name: str, limit: int) -> Iterator[Dict[str, Any]]:
        """
        Yields standardized dicts for hashtag posts.
        """
        self._load_session()
        hashtag_clean = re.sub(r'[^a-zA-Z0-9]', '', hashtag_name).lower()
        logger.info(f"[Hashtag Fetcher] Initializing for #{hashtag_clean} (Limit: {limit})")
        hashtag_obj = instaloader.Hashtag.from_name(self.L.context, hashtag_clean)
        
        count = 0
        try:
            for post in hashtag_obj.get_top_posts():
                if count >= limit: return
                if post.is_video:
                    yield self._standardize_post(post)
                    count += 1
        except Exception as e:
            logger.warning(f"Standard fetch failed: {e}, using robust fallback...")

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
                            m = item.get("media") or item.get("clips") or item
                            if isinstance(m, dict) and "clips" in m:
                                m = m["clips"].get("media", m["clips"])
                            if isinstance(m, dict) and (m.get("is_video") or m.get("video_duration")):
                                post = instaloader.Post.from_iphone_struct(self.L.context, m)
                                yield self._standardize_post(post)
                                count += 1
            except Exception as e:
                logger.error(f"Robust fetch failed: {e}")

    def _fetch_from_profile(self, username: str, limit: int) -> Iterator[Dict[str, Any]]:
        """
        Yields standardized dicts for profile Reels.
        """
        self._load_session()
        username_clean = username.strip().replace("@", "").lower()
        logger.info(f"[Profile Fetcher] Initializing for @{username_clean} (Limit: {limit})")
        profile = instaloader.Profile.from_name(self.L.context, username_clean)
        
        count = 0
        for post in profile.get_reels():
            if count >= limit: break
            yield self._standardize_post(post)
            count += 1

    def _standardize_post(self, post: instaloader.Post) -> Dict[str, Any]:
        """
        Converts instaloader.Post to standardized dictionary.
        """
        return {
            "video_url": str(post.video_url),
            "source_id": str(post.shortcode),
            "source_url": f"https://www.instagram.com/p/{post.shortcode}/",
            "author_username": post.owner_username,
            "original_caption": post.caption if post.caption else "",
            "duration": int(post.video_duration) if post.video_duration else 0
        }

    async def execute_job(self, job_id: str, target: str, crawl_type: str, limit: int):
        """
        Override to call BaseScraper.execute_job with platform='instagram'
        """
        await super().execute_job(job_id, target, crawl_type, limit, platform="instagram")

instagram_scraper = InstagramScraper()
