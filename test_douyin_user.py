import asyncio
import httpx
import urllib.parse
from app.core.config import settings
from douyin_tiktok_scraper.scraper import Scraper

async def test_douyin_user_search():
    scraper = Scraper()
    keyword = "beplain"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cookie": settings.douyin_cookie
    }
    scraper.headers["User-Agent"] = headers["User-Agent"]
    
    url = (
        f"https://www.douyin.com/aweme/v1/web/discover/search/"
        f"?device_platform=webapp&aid=6383&channel=channel_pc_web"
        f"&search_channel=aweme_user_web&keyword={urllib.parse.quote(keyword)}"
        f"&search_source=normal_search&query_correct_type=1&is_filter_search=0&offset=0&count=10"
    )
    
    signed = scraper.generate_x_bogus_url(url)
    print("Signed URL:", signed)
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20) as http:
        resp = await http.get(signed)
        print("Status:", resp.status_code)
        try:
            data = resp.json()
            user_list = data.get("user_list", [])
            if user_list:
                first_user = user_list[0].get("user_info", {})
                print("Found user:", first_user.get("nickname"))
                print("sec_uid:", first_user.get("sec_uid"))
            else:
                print("No user_list found. keys:", data.keys())
        except Exception as e:
            print("Failed to parse JSON:", e, resp.text[:200])

if __name__ == "__main__":
    asyncio.run(test_douyin_user_search())
