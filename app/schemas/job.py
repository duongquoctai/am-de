from pydantic import BaseModel
from typing import Optional

class JobCreateRequest(BaseModel):
    keyword: str
    target_count: int = 5
    platform: str = "instagram"

class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    message: str
