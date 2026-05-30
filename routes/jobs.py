from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db.mongo import jobs_col, results_col, sessions_col, db
from bson import ObjectId
import uuid
from typing import Optional
from routes.auth import get_user_by_token

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

class JobCreate(BaseModel):
    title: str
    description: str

@router.post("/")
async def create_job(data: dict, user: dict = Depends(get_user_by_token)):
    """Create a new job description."""
    role = user.get("role")
    user_id = user.get("id")
    email = user.get("email")
    
    print(f"[DEBUG POST /api/jobs/] Request body: {data}")
    print(f"[DEBUG POST /api/jobs/] Authenticated user ID: {user_id}, role: {role}, email: {email}")
    
    if role != "recruiter":
        raise HTTPException(status_code=403, detail="Only recruiters can post jobs")
        
    job_id = f"jd_{uuid.uuid4().hex[:8]}"
    
    # Inject values
    data["job_id"] = job_id
    data["id"] = job_id
    data["recruiter_id"] = user_id
    data["created_by"] = user_id
    data["recruiter_email"] = email
    
    if "status" not in data:
        data["status"] = "open"
        
    print(f"[DEBUG POST /api/jobs/] Saving job data to DB: recruiter_id={data['recruiter_id']}, created_by={data['created_by']}, recruiter_email={data['recruiter_email']}")
    
    await jobs_col.insert_one(data)
    return {"message": "Job created", "job_id": job_id, "id": job_id}

@router.get("/")
async def list_jobs(
    recruiter_id: Optional[str] = None,
    created_by: Optional[str] = None,
    recruiter_email: Optional[str] = None,
    user: dict = Depends(get_user_by_token)
):
    """List all job descriptions."""
    query = {}
    print(f"[DEBUG GET /api/jobs/] Fetch request by User ID: {user.get('id')}, Role: {user.get('role')}, Email: {user.get('email')}")
    print(f"[DEBUG GET /api/jobs/] Input query filters - recruiter_id: {recruiter_id}, created_by: {created_by}, recruiter_email: {recruiter_email}")
    
    if user.get("role") == "recruiter":
        # Force recruiter to only see their own jobs
        user_id = user["id"]
        user_email = user["email"]
        query["$or"] = [
            {"recruiter_id": user_id},
            {"created_by": user_id},
            {"recruiter_email": user_email}
        ]
    else:
        # Candidate/Admin - check optional filters
        or_conditions = []
        if recruiter_id:
            or_conditions.append({"recruiter_id": recruiter_id})
        if created_by:
            or_conditions.append({"created_by": created_by})
        if recruiter_email:
            or_conditions.append({"recruiter_email": recruiter_email})
            
        if or_conditions:
            query["$or"] = or_conditions

    print(f"[DEBUG GET /api/jobs/] Database query filter applied: {query}")
    jobs = await jobs_col.find(query, {"_id": 0}).to_list(length=1000)
    for job in jobs:
        if "id" not in job and "job_id" in job:
            job["id"] = job["job_id"]
            
    print(f"[DEBUG GET /api/jobs/] Found {len(jobs)} jobs.")
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
    print(f"[DEBUG PUT /api/jobs/{job_id}] Request body received: {data}")
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
