import asyncio
from app.services.tiktok_douyin_service import tiktok_douyin_scraper
from app.core.config import settings

async def main():
    print("Using TikTok Cookie length:", len(settings.tiktok_cookie))
    
    # Run the hashtag search logic directly
    print("Executing job...")
    try:
        await tiktok_douyin_scraper.execute_job(
            job_id="30a54d71-f9cc-46d3-8b88-cbe97f493b6f",
            target="techwoven",
            crawl_type="hashtag",
            limit=2,
            platform="tiktok"
        )
        print("Job finished!")
    except Exception as e:
        print(f"Job failed with exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
