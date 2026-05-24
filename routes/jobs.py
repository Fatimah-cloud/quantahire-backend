from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.mongo import jobs_col
from bson import ObjectId
import uuid

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

class JobCreate(BaseModel):
    title: str
    description: str

@router.post("/")
async def create_job(job: JobCreate):
    """Create a new job description."""
    job_id   = f"jd_{uuid.uuid4().hex[:8]}"
    job_data = {
        "job_id":      job_id,
        "title":       job.title,
        "description": job.description,
    }
    await jobs_col.insert_one(job_data)
    return {"message": "Job created", "job_id": job_id}

@router.get("/")
async def list_jobs():
    """List all job descriptions."""
    jobs = await jobs_col.find({}, {"_id": 0}).to_list(length=1000)
    return {"count": len(jobs), "jobs": jobs}

@router.get("/{job_id}")
async def get_job(job_id: str):
    job = await jobs_col.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.delete("/{job_id}")
async def delete_job(job_id: str):
    result = await jobs_col.delete_one({"job_id": job_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": f"Deleted job: {job_id}"}
