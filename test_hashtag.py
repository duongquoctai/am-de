import asyncio
import httpx
import urllib.parse
import json
from douyin_tiktok_scraper.scraper import Scraper

async def test_hashtag():
    tag = "techwoven"
    scraper = Scraper()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.tiktok.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": "_ttp=2kdGAQc59bNWyiHg3JvfrG8nUmm; _ga=GA1.1.1955890799.1748489461; uid_tt=af042a69181c0646c4f70e5b74998ed556d6368f58f2f214c95046eb5ea6c6f4; uid_tt_ss=af042a69181c0646c4f70e5b74998ed556d6368f58f2f214c95046eb5ea6c6f4; sid_tt=4a5ed8bb7daae92fb1722af614f5c3ab; sessionid=4a5ed8bb7daae92fb1722af614f5c3ab; sessionid_ss=4a5ed8bb7daae92fb1722af614f5c3ab; store-idc=alisg; store-country-code=vn; store-country-code-src=uid; tt-target-idc=alisg; tt-target-idc-sign=DIrVTOiLG0pT0_1fOe5Dyvwi6F7I-gA5akph4Y5uA3kMTl0TqBheRDZLDE486RoUdzhgZzvguto1Cq4E5azNQdZMry8UPTXO5BvG1WI2tNW9E5Xq9-drAe4598FzI-zQRObh9KlOeGHTeb_XOX-fZIQfg-OMsCNtAW1DcsF-9ZCyKRs683WZPOFJb3-OrnAfJeCdQUd_H8OxskvUj8w9mZD0fnJT5VguTfAs1eSi9Ks5WriRckq4_rYpg_c_7pSHu0mrAnm8EHr0ykpvUit33FzH-5yLSqs4Uka9m-d35UCuzMWrM_V56rlFCji5owZPhHLuPNWUWwhtCuRrUVDLz5H9XJXrB8l4SPT_GuiKSHh9MSR2D3B3hXOcDyp8JoFz4fFhhNeqv87ASt37-nfeLFSEP9GzSl_WEDFN5EE6FtEr2JauVYMsozXey3m3L5sZKC4pB8Pb9tNdo10TuBWBggDBM06jVOb_7yV9_PHxEnEnq-C21aHE2fw0FNuvQS8c; _ga_LWWPCY99PB=GS1.1.1748491723.2.1.1748491726.0.0.1510133051; tt_chain_token=Rmo+dNGeMfUW+SLIqoBOZA==; tt_csrf_token=ioTEia8b-oghrcHKK2gzix68ZdP7vOaLaE8g; s_v_web_id=verify_mnycr9i7_MJkEK41v_YHXt_49hb_9QnF_cxXvgMsESzgh; sid_guard=4a5ed8bb7daae92fb1722af614f5c3ab%7C1778728565%7C15552000%7CTue%2C+10-Nov-2026+03%3A16%3A05+GMT; tt_session_tlb_tag=sttt%7C3%7CSl7Yu32q6S-xcir2FPXDq__________QGNrieSo3DQrgO7Klf9oHzBjFdqPTHrwHrldqVlXWfog%3D; sid_ucp_v1=1.0.1-KDA3OTZjYWY0NTkwZGI4YzVhMTY2OTExZmZkNjUyNDk5Nzg0NmZkZjUKGQiBiLSk7dbzx2AQ9fyU0AYYsws4CEASSAQQAxoDc2cxIiA0YTVlZDhiYjdkYWFlOTJmYjE3MjJhZjYxNGY1YzNhYjJOCiBXMdtopwPHnS19lLFfSVtrKkc-5Nr3UJzYuXshansjmBIgXEUSM3AAMr8g7V6wI202xZ2dYMA6D1Ky4rpYFknS1eMYBSIGdGlrdG9r; ssid_ucp_v1=1.0.1-KDA3OTZjYWY0NTkwZGI4YzVhMTY2OTExZmZkNjUyNDk5Nzg0NmZkZjUKGQiBiLSk7dbzx2AQ9fyU0AYYsws4CEASSAQQAxoDc2cxIiA0YTVlZDhiYjdkYWFlOTJmYjE3MjJhZjYxNGY1YzNhYjJOCiBXMdtopwPHnS19lLFfSVtrKkc-5Nr3UJzYuXshansjmBIgXEUSM3AAMr8g7V6wI202xZ2dYMA6D1Ky4rpYFknS1eMYBSIGdGlrdG9r; odin_tt=b8c661cbe39e2704da240935a4338615d030efadaa60c7dce508241d5aabab2b15922e6c9ab1dcb400e9795df397081eee917552831fafdf7dd49bd7e979f38fe1c113eddce1920e9123d7c0ac29dbe2; ttwid=1%7CHyym_T1Vbb4TLLIctBVOKc2yVasLfDjNXw9PzZuKdhk%7C1778842885%7C7daf7f59d83a2ba4a4134d61135d2840848a6148aa7349de57a5e4372631d5f4; store-country-sign=MEIEDB6R3AqRG3onCTboXAQgt3ryEoG87o_wgfqtoMe6zznLTnPImWHVvu2c9iSfhkIEELnFG-3zwtBAISBfcFzsyd4; msToken=L6w--3SRS2BLLuqQJizUA8-6jJiDcrWDOGxkrClTginr4xm21G7_WUBIxreJgx8kudVSJeUZwU-WEZhziI5IdW_osMmtrVVrz21rbj9Z5b9BCjN-rLTrMJr2Y7NWEWztapCkLOAVl5WqI9KdCLCeKJI="
    }
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, cookies=httpx.Cookies(), timeout=20) as http:
        # Pre-auth
        resp = await http.get("https://www.tiktok.com/")
        print("ttwid cookies:", [c.name for c in http.cookies.jar])
        
        # Hashtag test
        url = (
            f"https://www.tiktok.com/api/search/item/full/"
            f"?aid=1988&keyword={urllib.parse.quote('#' + tag)}"
            f"&count=10&cursor=0"
        )
        signed = scraper.generate_x_bogus_url(url)
        print("Signed URL:", signed)
        
        tag_resp = await http.get(signed)
        print("Status:", tag_resp.status_code)
        print("Content-Length:", len(tag_resp.text))
        if len(tag_resp.text) > 0:
            print("Content start:", tag_resp.text[:200])
        else:
            print("EMPTY BODY!")

if __name__ == "__main__":
    asyncio.run(test_hashtag())
