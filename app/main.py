from fastapi import FastAPI, BackgroundTasks, HTTPException
from app.schemas.job import JobCreateRequest, JobCreateResponse
from app.services.supabase_service import supabase_service
from app.workers.job_dispatcher import process_crawl_job

app = FastAPI(title="AM Data Engine")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "AM Data Engine API is running"}

@app.post("/api/jobs/crawl", response_model=JobCreateResponse, status_code=202)
def create_crawl_job(request: JobCreateRequest, background_tasks: BackgroundTasks):
    try:
        # Create initial pending job and get job_id
        job_id = supabase_service.create_job(
            keyword=request.keyword, 
            platform=request.platform, 
            target_count=request.target_count
        )
        
        # Queue the job parsing sequence using FastAPI BackgroundTasks
        background_tasks.add_task(
            process_crawl_job,
            job_id=job_id,
            keyword=request.keyword,
            platform=request.platform,
            target_count=request.target_count
        )
        
        return JobCreateResponse(
            job_id=job_id,
            status="pending",
            message="Job queued successfully and running in background"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue crawl job: {str(e)}")
