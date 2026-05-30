from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.mongo import jobs_col, results_col, sessions_col, db
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
        "status":      "open",
    }
    await jobs_col.insert_one(job_data)
    return {"message": "Job created", "job_id": job_id}

@router.get("/")
async def list_jobs():
    """List all job descriptions."""
    jobs = await jobs_col.find({}, {"_id": 0}).to_list(length=1000)
    for job in jobs:
        if "id" not in job and "job_id" in job:
            job["id"] = job["job_id"]
    return jobs

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

@router.put("/{job_id}")
async def update_job(job_id: str, data: dict):
    """Update a job description and reset all its feedback history/matching sessions."""
    # 1. Update the job details in the jobs collection
    data.pop("_id", None)
    data.pop("id", None)
    data.pop("job_id", None)

    query = {"$or": [{"id": job_id}, {"job_id": job_id}]}
    result = await jobs_col.update_one(query, {"$set": data})

    updated_job = await jobs_col.find_one(query, {"_id": 0})
    if not updated_job:
        raise HTTPException(status_code=404, detail="Job not found")

    # 2. Reset / clear feedback history and matching sessions:
    # A. Delete matching sessions for this job from 'sessions' collection
    await sessions_col.delete_many({"job_id": job_id})

    # B. Delete saved ranking results for this job from 'results' collection
    await results_col.delete_many({"job_id": job_id})

    # C. Reset candidate application statuses for this job back to "processed" (clears shortlist/reject)
    application_col = db["applications"]
    await application_col.update_many(
        {"job_id": job_id},
        {"$set": {"status": "processed"}}
    )

    return updated_job
