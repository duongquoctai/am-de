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
        
        # Ensure the internal scraper uses our User-Agent for X-Bogus signing
        self._scraper.headers["User-Agent"] = self._headers["User-Agent"]

    # -- helpers -------------------------------------------------------------

    async def _pre_auth(self, http: httpx.AsyncClient) -> None:
        """
        Visit tiktok.com to obtain ttwid/msToken cookies.
        The server sets ttwid via Set-Cookie; httpx stores it automatically.
        This is required — every TikTok API endpoint checks for a valid ttwid.
        """
        logger.info("[TikTok] _pre_auth: hitting homepage to get ttwid...")
        resp = await http.get("https://www.tiktok.com/")
        resp.raise_for_status()
        set_cookies = http.cookies.jar
        ttwid_found = any(c.name == "ttwid" for c in set_cookies)
        if not ttwid_found:
            logger.warning(
                "[TikTok] _pre_auth: ttwid NOT in Set-Cookie. "
                "All cookies present: %s",
                [c.name for c in set_cookies],
            )
        else:
            logger.info("[TikTok] _pre_auth: ttwid obtained successfully")

    def _safe_json(self, resp: httpx.Response, endpoint: str) -> dict:
        """Parse JSON with detailed error info; handle empty body gracefully."""
        raw = resp.text or ""
        if not raw.strip():
            raise RuntimeError(
                f"[TikTok] {endpoint} returned empty body "
                f"(status={resp.status_code}, content-type={resp.headers.get('content-type', '')})"
            )
        try:
            return resp.json()
        except Exception as exc:
            ct = resp.headers.get("content-type", "")
            logger.error(
                "[TikTok] %s returned non-JSON | status=%s content-type=%s body=%s",
                endpoint, resp.status_code, ct, raw[:200],
            )
            raise RuntimeError(
                f"[TikTok] {endpoint} response is not parseable JSON "
                f"(status={resp.status_code}): {raw[:200]}"
            ) from exc

    def _is_waf_challenge(self, text: str) -> bool:
        """Detect WAF/captcha challenge pages."""
        signatures = (
            "slardar", "challenge", "captcha", "verify",
            "access denied", "blocked", "slardar-waf",
            "cf-chl-bypass",
        )
        lower = (text or "")[:1000].lower()
        return any(s in lower for s in signatures)

    def _extract_rehydration_json(self, html: str) -> dict:
        """Extract the SSR JSON blob from tiktok profile HTML."""
        if self._is_waf_challenge(html):
            raise RuntimeError(
                "[TikTok] WAF/captcha challenge detected on profile page. "
                "Your tiktok_cookie is invalid, expired, or from a restricted region. "
                "Get a fresh cookie from browser DevTools → Network → copy Cookie header."
            )

        m = re.search(
            r'<script\s+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"\s+type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not m:
            raise RuntimeError(
                "[TikTok] Cannot find __UNIVERSAL_DATA_FOR_REHYDRATION__ in profile HTML. "
                "Cookie invalid or profile is private/non-existent."
            )
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            inner_preview = m.group(1)[:200]
            raise RuntimeError(
                f"[TikTok] SSR JSON blob is malformed: {inner_preview[:200]}"
            ) from exc

    def _extract_sec_uid_from_scope(self, data: dict) -> str:
        """Navigate the __DEFAULT_SCOPE__ tree to find user.secUid."""
        scope = data.get("__DEFAULT_SCOPE__", {})
        user_detail = scope.get("webapp.user-detail", {})
        user_info = user_detail.get("userInfo", {})
        sec_uid = user_info.get("user", {}).get("secUid", "")
        if not sec_uid:
            available_keys = list(scope.keys()) if scope else []
            raise RuntimeError(
                f"[TikTok] secUid not in SSR JSON. Available scope keys: {available_keys}"
            )
        return sec_uid

    def _standardize_item(self, aweme: dict) -> Dict[str, Any] | None:
        """Convert a raw item from item_list / hashtag / search into our schema."""
        aweme_id = aweme.get("aweme_id") or aweme.get("id") or aweme.get("id_str")
        if not aweme_id:
            logger.debug(f"[TikTok] Skipping item without aweme_id, keys: {list(aweme.keys())[:6]}")
            return None

        video_block = aweme.get("video") or {}

        play_urls = video_block.get("playAddr", "") or \
                    video_block.get("play_addr", {}).get("url_list", [""])[0] or ""

        download_urls = video_block.get("downloadAddr", "") or \
                        video_block.get("download_addr", {}).get("url_list", [""])[0] or ""

        video_url = play_urls or download_urls or ""
        if not video_url:
            logger.warning(f"[TikTok] No video URL for aweme_id={aweme_id}")
            return None

        author = aweme.get("author") or {}
        author_name = author.get("uniqueId") or author.get("unique_id") or author.get("nickname", "")

        duration_ms = aweme.get("duration", 0)
        if isinstance(duration_ms, int):
            duration_ms = aweme.get("video", {}).get("duration", duration_ms)

        return {
            "video_url": video_url,
            "source_id": str(aweme_id),
            "source_url": f"https://www.tiktok.com/@{author.get('uniqueId', author_name) or author_name}/video/{aweme_id}",
            "author_username": author_name,
            "original_caption": aweme.get("desc", ""),
            "duration": int(duration_ms // 1000) if duration_ms else 0,
        }

    # -- fetchers  (all call _pre_auth so ttwid cookie is set)

    async def _fetch_from_profile(self, username: str, limit: int, platform: str = "tiktok") -> AsyncGenerator[Dict[str, Any], None]:
        username = username.replace("@", "").strip()
        logger.info(f"[TikTok] Fetching profile @{username} (limit={limit})")

        async with httpx.AsyncClient(headers=self._headers, follow_redirects=True, cookies=httpx.Cookies(), timeout=20) as http:
            # 0. Pre-auth — visit homepage so server sets ttwid
            await self._pre_auth(http)

            # 1. Resolve sec_uid from SSR
            profile_url = f"https://www.tiktok.com/@{username}"
            profile_resp = await http.get(profile_url)
            profile_resp.raise_for_status()
            if self._is_waf_challenge(profile_resp.text):
                raise RuntimeError("[TikTok] WAF challenge on profile page — cookie invalid")

            sec_uid = self._extract_sec_uid_from_scope(self._extract_rehydration_json(profile_resp.text))
            logger.info(f"[TikTok] resolved sec_uid={sec_uid}")

            # 2. Iterate item_list (http cookies jar already has ttwid)
            cursor = 0
            fetched = 0
            while fetched < limit:
                url = (
                    f"https://www.tiktok.com/api/post/item_list/"
                    f"?secUid={sec_uid}&count={min(limit - fetched, 30)}&cursor={cursor}"
                )
                try:
                    signed = self._scraper.generate_x_bogus_url(url)
                    item_resp = await http.get(signed)
                except Exception:
                    item_resp = await http.get(url)
                
                item_resp.raise_for_status()
                data = self._safe_json(item_resp, "item_list")
                items = data.get("item_list") or data.get("itemList") or data.get("aweme_list") or []
                for item in items:
                    std = self._standardize_item(item)
                    if std:
                        yield std
                        fetched += 1
                        if fetched >= limit:
                            break
                has_more = data.get("hasMore", data.get("has_more", False))
                if not has_more:
                    break
                cursor = data.get("cursor", cursor + 30)

        logger.info(f"[TikTok] profile @{username} total fetched={fetched}")

    async def _fetch_from_hashtag(self, hashtag: str, limit: int, platform: str = "tiktok") -> AsyncGenerator[Dict[str, Any], None]:
        tag = hashtag.lstrip("#").strip()
        logger.info(f"[TikTok] Fetching hashtag #{tag} (limit={limit}) by redirecting to keyword search.")
        
        # TikTok's /api/tag/item_list is currently blocking or returning 'url doesn't match'
        # The search API is more reliable.
        async for item in self._fetch_from_keyword(f"#{tag}", limit, platform):
            yield item

    async def _fetch_from_keyword(self, keyword: str, limit: int, platform: str = "tiktok") -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"[TikTok] Search keyword '{keyword}' (limit={limit})")

        async with httpx.AsyncClient(headers=self._headers, follow_redirects=True, timeout=20) as http:
            await self._pre_auth(http)
            
            cookie_str = self._headers.get("Cookie", "")
            logger.info(f"[TikTok] Using cookie: {'YES (len=' + str(len(cookie_str)) + ')' if cookie_str else 'NO'}")
            
            cursor = 0
            fetched = 0
            while fetched < limit:
                url = (
                    f"https://www.tiktok.com/api/search/item/full/"
                    f"?aid=1988&keyword={urllib.parse.quote(keyword)}"
                    f"&count={min(limit - fetched, 30)}&cursor={cursor}"
                )
                try:
                    signed = self._scraper.generate_x_bogus_url(url)
                    logger.info(f"[TikTok] Signed search URL: {signed}")
                    search_resp = await http.get(signed)
                except Exception as e:
                    logger.error(f"[TikTok] X-Bogus signing failed: {e}")
                    search_resp = await http.get(url)

                search_resp.raise_for_status()
                data = self._safe_json(search_resp, f"search '{keyword}'")
                items = data.get("item_list") or data.get("itemList") or data.get("data") or []
                for item in items:
                    aweme = item.get("aweme_info") or item
                    std = self._standardize_item(aweme)
                    if std:
                        yield std
                        fetched += 1
                        if fetched >= limit:
                            break
                has_more = data.get("has_more", data.get("hasMore", False))
                if not has_more:
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

    def _safe_json(self, resp: httpx.Response, endpoint: str) -> dict:
        """Parse JSON from response with detailed error logging."""
        try:
            return resp.json()
        except Exception as exc:
            status = resp.status_code
            ct = resp.headers.get("content-type", "")
            preview = (resp.text or "")[:300]
            logger.error(
                f"[Douyin] {endpoint} returned non-JSON | "
                f"status={status} content-type={ct} | body preview: {preview[:200]}"
            )
            raise RuntimeError(
                f"[Douyin] {endpoint} did not return JSON "
                f"(status={status}, content-type={ct}): {preview[:200]}"
            ) from exc

    def _sign_url(self, url: str) -> str:
        try:
            return self._scraper.generate_x_bogus_url(url)
        except Exception as exc:
            logger.warning(f"[Douyin] X-Bogus signing failed: {exc}, returning unsigned URL")
            return url

    def _standardize_item(self, aweme: dict) -> Dict[str, Any] | None:
        aweme_id = aweme.get("aweme_id") or aweme.get("id") or aweme.get("id_str")
        if not aweme_id:
            logger.debug(f"[Douyin] Skipping item without aweme_id, keys: {list(aweme.keys())[:6]}")
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

    async def _fetch_from_profile(self, douyin_target: str, limit: int, platform: str = "douyin") -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"[Douyin] Fetching profile target={douyin_target} (limit={limit})")

        # Clean up the target
        douyin_target = douyin_target.strip().split("?")[0]
        
        if douyin_target.startswith("http"):
            url = douyin_target
        elif douyin_target.startswith("MS4wLj"):
            url = f"https://www.douyin.com/user/{douyin_target}"
        elif len(douyin_target) <= 8:
            url = f"https://v.douyin.com/{douyin_target}/"
        else:
            url = f"https://www.douyin.com/user/{douyin_target}"

        async with httpx.AsyncClient(headers=self._headers, follow_redirects=True, timeout=20) as http:
            html_resp = await http.get(url)
            html_resp.raise_for_status()

            if any(s in html_resp.text.lower() for s in ("security check", "verify", "captcha", "challenge")):
                raise RuntimeError(
                    "[Douyin] WAF/captcha challenge detected. "
                    "Your douyin_cookie is invalid or expired. "
                    "Get a fresh cookie from douyin.com."
                )

            sec_uid_match = re.search(r'"secUid":"([^"]+)"', html_resp.text)
            if not sec_uid_match:
                preview = html_resp.text[:300]
                raise RuntimeError(f"[Douyin] Could not extract sec_uid from profile HTML. "
                                   f"Cookie may be missing or invalid. HTML preview: {preview}")
            sec_uid = sec_uid_match.group(1)

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
                data = self._safe_json(item_resp, f"profile {douyin_short_code}")
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

    async def _fetch_from_hashtag(self, hashtag: str, limit: int, platform: str = "douyin") -> AsyncGenerator[Dict[str, Any], None]:
        tag = hashtag.lstrip("#").strip()
        logger.info(f"[Douyin] Fetching hashtag #{tag} (limit={limit}) by redirecting to keyword search.")
        async for item in self._fetch_from_keyword(f"#{tag}", limit, platform):
            yield item

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
                data = self._safe_json(search_resp, f"search '{keyword}'")
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
