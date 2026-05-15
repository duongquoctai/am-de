from app.services.instaloader_service import instagram_scraper
from app.services.tiktok_douyin_service import tiktok_douyin_scraper
from app.services.supabase_service import supabase_service

async def process_crawl_job(job_id: str, target: str, crawl_type: str, target_count: int, platform: str = "instagram"):
    """
    Orchestrator that delegates to the specialized scraper service.
    """
    print(f"process_crawl_job | ID: {job_id} | Target: {target} | Type: {crawl_type} | Count: {target_count} | Platform: {platform}")
    platform_lower = platform.lower()
    if platform_lower == "instagram":
        await instagram_scraper.execute_job(
            job_id=job_id,
            target=target,
            crawl_type=crawl_type,
            limit=target_count
        )
    elif platform_lower in ["tiktok", "douyin"]:
        await tiktok_douyin_scraper.execute_job(
            job_id=job_id,
            target=target,
            crawl_type=crawl_type,
            limit=target_count,
            platform=platform_lower,
        )
    else:
        error_msg = f"Platform '{platform}' is not supported yet."
        supabase_service.update_job_status(job_id, status="failed", error_message=error_msg)
