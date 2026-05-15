import json
import logging
import urllib.parse
import time
import re
import httpx
from typing import AsyncGenerator, Dict, Any, Optional

from app.services.base_scraper import BaseScraper
from app.core.config import settings
from douyin_tiktok_scraper.scraper import Scraper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TikTok
# ---------------------------------------------------------------------------

class TikTokScraper(BaseScraper):
    """Crawl TikTok via internal web API endpoints (no per-video detail calls)."""

    def __init__(self):
        super().__init__()
        self._scraper = Scraper()
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.tiktok.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        cookie = getattr(settings, "tiktok_cookie", None)
        if cookie:
            self._headers["Cookie"] = cookie

    # -- helpers -------------------------------------------------------------

    def _extract_rehydration_json(self, html: str) -> dict:
        """Extract the SSR JSON blob from tiktok profile HTML."""
        m = re.search(
            r'<script\s+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"\s+type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not m:
            raise RuntimeError("[TikTok] Cannot find __UNIVERSAL_DATA_FOR_REHYDRATION__ in HTML. "
                               "Cookie may be missing or invalid.")
        return json.loads(m.group(1))

    def _extract_sec_uid_from_scope(self, data: dict) -> str:
        """Navigate the __DEFAULT_SCOPE__ tree to find user.secUid."""
        scope = data.get("__DEFAULT_SCOPE__", {})
        user_detail = scope.get("webapp.user-detail", {})
        user_info = user_detail.get("userInfo", {})
        sec_uid = user_info.get("user", {}).get("secUid", "")
        if not sec_uid:
            raise RuntimeError("[TikTok] secUid not found in SSR JSON.")
        return sec_uid

    def _standardize_item(self, aweme: dict) -> Dict[str, Any] | None:
        """Convert a raw item from item_list / hashtag / search into our schema."""
        aweme_id = aweme.get("aweme_id") or aweme.get("id") or aweme.get("id_str")
        if not aweme_id:
            return None

        video_block = aweme.get("video") or {}

        play_urls = video_block.get("playAddr", "") or \
                    video_block.get("play_addr", {}).get("url_list", [""])[0] or ""

        download_urls = video_block.get("downloadAddr", "") or \
                        video_block.get("download_addr", {}).get("url_list", [""])[0] or ""

        video_url = play_urls or download_urls or ""

        author = aweme.get("author") or {}
        author_name = author.get("uniqueId") or author.get("unique_id") or author.get("nickname", "")

        duration_ms = aweme.get("duration", 0)
        if isinstance(duration_ms, int):
            duration_ms = aweme.get("video", {}).get("duration", duration_ms)

        return {
            "video_url": video_url,
            "source_id": str(aweme_id),
            "source_url": f"https://www.tiktok.com/@{author.get('uniqueId', author_name)}/video/{aweme_id}",
            "author_username": author_name,
            "original_caption": aweme.get("desc", ""),
            "duration": int(duration_ms // 1000) if duration_ms else 0,
        }

    # -- fetchers ------------------------------------------------------------

    async def _fetch_from_profile(self, username: str, limit: int, platform: str = "tiktok") -> AsyncGenerator[Dict[str, Any], None]:
        username = username.replace("@", "").strip()
        logger.info(f"[TikTok] Fetching profile @{username} (limit={limit})")

        async with httpx.AsyncClient(headers=self._headers, follow_redirects=True, timeout=20) as http:
            # 1. Resolve sec_uid from SSR
            profile_url = f"https://www.tiktok.com/@{username}"
            resp = await http.get(profile_url)
            resp.raise_for_status()

            sec_uid = self._extract_sec_uid_from_scope(self._extract_rehydration_json(resp.text))
            logger.info(f"[TikTok] resolved sec_uid={sec_uid}")

            # 2. Iterate item_list (avoids per-video detail call)
            cursor = 0
            fetched = 0
            while fetched < limit:
                url = (
                    f"https://www.tiktok.com/api/post/item_list/"
                    f"?secUid={sec_uid}&count={min(limit - fetched, 35)}&cursor={cursor}"
                )
                item_resp = await http.get(url)
                item_resp.raise_for_status()
                data = item_resp.json()
                items = data.get("aweme_list") or []
                for item in items:
                    std = self._standardize_item(item)
                    if std:
                        yield std
                        fetched += 1
                        if fetched >= limit:
                            break
                if not data.get("hasMore", False):
                    break
                cursor = data.get("cursor", cursor + 35)

        logger.info(f"[TikTok] profile @{username} total fetched={fetched}")

    async def _fetch_from_hashtag(self, hashtag: str, limit: int, platform: str = "tiktok") -> AsyncGenerator[Dict[str, Any], None]:
        tag = hashtag.lstrip("#").strip()
        logger.info(f"[TikTok] Fetching hashtag #{tag} (limit={limit})")

        async with httpx.AsyncClient(headers=self._headers, follow_redirects=True, timeout=20) as http:
            cursor = 0
            fetched = 0
            while fetched < limit:
                url = (
                    f"https://www.tiktok.com/api/recommend/item-list/"
                    f"?aid=1988&app_language=en&app_name=tiktok_web&"
                    f"web_id=0&count={min(limit - fetched, 30)}&cursor={cursor}"
                )
                hashtag_resp = await http.get(url)
                hashtag_resp.raise_for_status()
                data = hashtag_resp.json()
                items = data.get("itemList") or data.get("items") or data.get("aweme_list") or []
                for item in items:
                    std = self._standardize_item(item)
                    if std:
                        yield std
                        fetched += 1
                        if fetched >= limit:
                            break
                if not data.get("hasMore", False):
                    break
                cursor = data.get("cursor", cursor + 30)

        logger.info(f"[TikTok] hashtag #{tag} total fetched={fetched}")

    async def _fetch_from_keyword(self, keyword: str, limit: int, platform: str = "tiktok") -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"[TikTok] Search keyword '{keyword}' (limit={limit})")

        async with httpx.AsyncClient(headers=self._headers, follow_redirects=True, timeout=20) as http:
            cursor = 0
            fetched = 0
            while fetched < limit:
                url = (
                    f"https://www.tiktok.com/api/search/item/full/"
                    f"?aid=1988&keyword={urllib.parse.quote(keyword)}&search_id=&"
                    f"search_source=history&enter_from=&search_duration=0&"
                    f"search_group_id=&type=1&history_verification_token=&"
                    f"need_filter_item=false&source=0&is_edit_query=false&"
                    f"aid_string_on_web=1&count={min(limit - fetched, 30)}&cursor={cursor}"
                )
                # Sign with X-Bogus (Douyin X-Bogus)
                try:
                    signed = self._scraper.generate_x_bogus_url(url)
                    search_resp = await http.get(signed)
                except Exception:
                    search_resp = await http.get(url)

                search_resp.raise_for_status()
                data = search_resp.json()
                items = data.get("itemList") or data.get("data") or []
                for item in items:
                    std = self._standardize_item(item)
                    if std:
                        yield std
                        fetched += 1
                        if fetched >= limit:
                            break
                if not data.get("has_more", False):
                    break
                cursor = data.get("cursor", cursor + 30)

        logger.info(f"[TikTok] keyword '{keyword}' total fetched={fetched}")

    # -- orchestrator --------------------------------------------------------

    async def execute_job(self, job_id: str, target: str, crawl_type: str, limit: int):
        await super().execute_job(job_id, target, crawl_type, limit, platform="tiktok")


# ---------------------------------------------------------------------------
# Douyin
# ---------------------------------------------------------------------------

class DouyinScraper(BaseScraper):
    """Crawl Douyin via web API (X-Bogus signed)."""

    def __init__(self):
        super().__init__()
        self._scraper = Scraper()
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json;text/application/json,application/*;q=0.9",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        cookie = getattr(settings, "douyin_cookie", None)
        if cookie:
            self._headers["Cookie"] = cookie
        # Also set scraper-level headers
        self._scraper.douyin_api_headers.update(self._headers)

    def _sign_url(self, url: str) -> str:
        try:
            return self._scraper.generate_x_bogus_url(url)
        except Exception as exc:
            logger.warning(f"[Douyin] X-Bogus signing failed: {exc}, returning unsigned URL")
            return url

    def _standardize_item(self, aweme: dict) -> Dict[str, Any] | None:
        aweme_id = aweme.get("aweme_id") or aweme.get("id") or aweme.get("id_str")
        if not aweme_id:
            return None
        video_block = aweme.get("video") or {}
        play_urls = video_block.get("playAddr", "") or video_block.get("play_addr", {}).get("url_list", [""])[0] or ""
        download_urls = video_block.get("downloadAddr", "") or video_block.get("download_addr", {}).get("url_list", [""])[0] or ""
        video_url = play_urls or download_urls or ""
        if "playwm" in video_url:
            video_url = video_url.replace("playwm", "play")
        return {
            "video_url": video_url,
            "source_id": str(aweme_id),
            "source_url": f"https://www.douyin.com/video/{aweme_id}",
            "author_username": (aweme.get("author") or {}).get("unique_id") or (aweme.get("author") or {}).get("nickname", ""),
            "original_caption": aweme.get("desc", ""),
            "duration": int(((aweme.get("duration", 0)) or (video_block.get("duration", 0) or 0)) / 1000),
        }

    async def _fetch_from_profile(self, douyin_short_code: str, limit: int, platform: str = "douyin") -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"[Douyin] Fetching profile short_code={douyin_short_code} (limit={limit})")

        if len(douyin_short_code) <= 8:
            url = f"https://www.douyin.com/ {douyin_short_code}"
        else:
            url = f"https://www.douyin.com/user/{douyin_short_code}"

        async with httpx.AsyncClient(headers=self._headers, follow_redirects=True, timeout=20) as http:
            html_resp = await http.get(url)
            html_resp.raise_for_status()

            sec_uid = re.search(r'"secUid":"([^"]+)"', html_resp.text)
            if not sec_uid:
                preview = html_resp.text[:300]
                raise RuntimeError(f"[Douyin] Could not extract sec_uid from profile HTML. "
                                   f"Cookie may be missing or invalid. HTML preview: {preview}")
            sec_uid = sec_uid.group(1)

            cursor = 0
            fetched = 0
            while fetched < limit:
                base = (
                    f"https://www.douyin.com/aweme/v1/web/aweme/post/"
                    f"?device_platform=webapp&aid=6383&channel=channel_pc_web&"
                    f"sec_user_id={sec_uid}&max_cursor={cursor}&count={min(limit - fetched, 35)}&"
                    f"publish_video_strategy_type=2&version_code=190500&version_name=19.5.0"
                )
                signed = self._sign_url(base)
                item_resp = await http.get(signed)
                item_resp.raise_for_status()
                data = item_resp.json()
                items = data.get("aweme_list") or data.get("awemeData") or []
                for item in items:
                    std = self._standardize_item(item)
                    if std:
                        yield std
                        fetched += 1
                        if fetched >= limit:
                            break
                if not data.get("has_more", False):
                    break
                cursor = data.get("max_cursor", cursor + 35)

        logger.info(f"[Douyin] profile short_code={douyin_short_code} total fetched={fetched}")

    async def _fetch_from_keyword(self, keyword: str, limit: int, platform: str = "douyin") -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"[Douyin] Search keyword '{keyword}' (limit={limit})")

        async with httpx.AsyncClient(headers=self._headers, follow_redirects=True, timeout=20) as http:
            cursor = 0
            fetched = 0
            while fetched < limit:
                base = (
                    f"https://www.douyin.com/aweme/v1/web/general/search/single/"
                    f"?device_platform=webapp&aid=6383&channel=channel_pc_web&"
                    f"search_channel=aweme_user_search_general&"
                    f"keyword={urllib.parse.quote(keyword)}&"
                    f"search_source=normal_search&"
                    f"query_correct_type=1&is_filter_search=true&"
                    f"from_group_id=&offset={cursor}&count={min(limit - fetched, 30)}"
                )
                signed = self._sign_url(base)
                search_resp = await http.get(signed)
                search_resp.raise_for_status()
                data = search_resp.json()
                items = data.get("data", [])
                if isinstance(items, list):
                    for item in items:
                        std = self._standardize_item(item)
                        if std:
                            yield std
                            fetched += 1
                            if fetched >= limit:
                                break
                if not data.get("has_more", False):
                    break
                cursor += 30

        logger.info(f"[Douyin] keyword '{keyword}' total fetched={fetched}")

    async def execute_job(self, job_id: str, target: str, crawl_type: str, limit: int):
        await super().execute_job(job_id, target, crawl_type, limit, platform="douyin")


# ---------------------------------------------------------------------------
# Router / legacy alias
# ---------------------------------------------------------------------------

_tiktok_instance = TikTokScraper()
_douyin_instance = DouyinScraper()


class TikTokDouyinScraper:
    """Facade that routes to TikTok or Douyin based on platform param."""

    async def execute_job(
        self,
        job_id: str,
        target: str,
        crawl_type: str,
        limit: int,
        platform: str = "tiktok",
    ):
        platform_lower = platform.lower()
        if platform_lower == "tiktok":
            await _tiktok_instance.execute_job(job_id, target, crawl_type, limit)
        elif platform_lower == "douyin":
            await _douyin_instance.execute_job(job_id, target, crawl_type, limit)
        else:
            raise ValueError(f"[Router] Unknown platform '{platform}'")


tiktok_douyin_scraper = TikTokDouyinScraper()
