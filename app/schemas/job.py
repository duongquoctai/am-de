from pydantic import BaseModel
from typing import Optional, Literal

class JobCreateRequest(BaseModel):
    job_id: Optional[str] = None
    target: str
    crawl_type: Literal["hashtag", "profile"]
    target_count: int = 5
    platform: str = "instagram"

class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    message: str
