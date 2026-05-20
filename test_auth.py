import asyncio
import httpx

async def test_auth():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20) as http:
        resp = await http.get("https://www.tiktok.com/")
        print("Status:", resp.status_code)
        print("Set-Cookie headers:", resp.headers.get_list("set-cookie"))
        print("Body length:", len(resp.text))
        print("Body preview:", resp.text[:500])

if __name__ == "__main__":
    asyncio.run(test_auth())
