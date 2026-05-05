import os
import uuid
import re
import httpx
import logging
from typing import AsyncGenerator, Tuple, Dict, Any
from instagrapi import Client
from instagrapi.exceptions import LoginRequired
from app.core.config import settings

logger = logging.getLogger(__name__)

class InstagrapiService:
    def __init__(self):
        self.cl = Client()
        # Add random human-mimicking delay to internal instagrapi API calls
        self.cl.delay_range = [1, 3] 
        
        self.session_file = getattr(settings, "ig_session_file", "ig_session.json")
        self.username = getattr(settings, "ig_username", "")
        self.password = getattr(settings, "ig_password", "")
            
        # Defer session initialization so it is not performed at module import time
        self.is_initialized = False

    def _initialize_session(self):
        if self.is_initialized:
            return

        if not self.username or not self.password:
            logger.warning("IG_USERNAME or IG_PASSWORD not set. Instagrapi may fail if session file doesn't exist.")

        session_loaded = False
        login_via_pw = False
        
        if os.path.exists(self.session_file):
            try:
                logger.info(f"Loading session settings from {self.session_file}")
                session = self.cl.load_settings(self.session_file)
                
                if session:
                    try:
                        self.cl.set_settings(session)
                        self.cl.login(self.username, self.password)
                        
                        try:
                            # Lightweight check on the authentication pool
                            self.cl.get_timeline_feed()
                            session_loaded = True
                            logger.info("Session loaded successfully.")
                        except LoginRequired:
                            logger.info("Session marked invalid. Dropping cookies while preserving Hardware Identity UUIDs...")
                            old_session = self.cl.get_settings()
                            
                            # Wipe out cookies natively
                            self.cl.set_settings({})
                            # Restoring device mapping cleanly prevents Instagram 'Device Hop' alerts
                            self.cl.set_uuids(old_session["uuids"])
                            
                            self.cl.login(self.username, self.password)
                            session_loaded = True
                            
                    except Exception as load_err:
                        logger.warning(f"Couldn't map session into backend safely: {load_err}")
            except Exception as e:
                logger.warning(f"Failed parsing existing session file: {e}")
                
        if not session_loaded:
            try:
                if self.username and self.password:
                    logger.info(f"Executing raw virgin footprint login for {self.username}")
                    if self.cl.login(self.username, self.password):
                        login_via_pw = True
            except Exception as l_err:
                logger.error(f"Couldn't execute login natively: {l_err}")
                raise l_err
                
            if not login_via_pw:
                raise ValueError("Valid session not found and login cleanly declined.")
                
        # Dump settings identically to build proxy hooks securely on disk
        self.cl.dump_settings(self.session_file)
        self.is_initialized = True

    def _clean_keyword(self, keyword: str) -> str:
        return re.sub(r'[^a-zA-Z0-9]', '', keyword).lower()

    async def _download_video(self, url: str, temp_dir: str) -> str:
        filename = f"{uuid.uuid4().hex}.mp4"
        filepath = os.path.join(temp_dir, filename)
        
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with open(filepath, 'wb') as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
        return filepath

    # Executing async logic natively via iterator wrappers
    async def get_top_media(self, keyword: str, target_count: int, temp_dir: str) -> AsyncGenerator[Tuple[str, Dict[str, Any]], None]:
        self._initialize_session()
        hashtag = self._clean_keyword(keyword)
        
        fetch_amount = target_count * 5  # Ensure density checks fetch properly evaluating media_type
        
        logger.info(f"Fetching top {fetch_amount} medias for #{hashtag}")
        medias = self.cl.hashtag_medias_top(name=hashtag, amount=fetch_amount)
        
        count = 0
        for media in medias:
            if count >= target_count:
                break
                
            if media.media_type == 2 and media.video_url:
                filepath = await self._download_video(str(media.video_url), temp_dir)
                
                metadata = {
                    "source_id": str(media.pk),
                    "source_url": f"https://www.instagram.com/p/{media.code}/" if media.code else None,
                    "author_username": media.user.username if media.user else "unknown",
                    "original_caption": media.caption_text if media.caption_text else "",
                    "duration": media.video_duration
                }
                
                yield filepath, metadata
                count += 1

instagrapi_service = InstagrapiService()
