import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from db.mongo import db
from bson import ObjectId
from routes.auth import get_user_by_token
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["Entities"])

def get_collection_name(plural_name: str) -> str:
    # Map kebab-case names like 'interview-slots' or 'psych-questions' to MongoDB collection names
    name = plural_name.replace("-", "_").lower()
    
    # Standard collections mapping
    mapping = {
        "jobs": "jobs",
        "applications": "applications",
        "candidates": "candidates",
        "recruiters": "recruiters",
        "admins": "admins",
        "interview_slots": "interview_slots",
        "assessments": "assessment_results",
        "psych_questions": "psych_questions",
        "notifications": "notifications",
        "assessment_results": "assessment_results"
    }
    return mapping.get(name, name)

def format_doc(doc: dict, col_name: str) -> dict:
    if not doc:
        return doc
        
    # Helper function to stringify BSON ObjectIds recursively
    def stringify_objectids(item):
        if isinstance(item, dict):
            return {k: stringify_objectids(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [stringify_objectids(x) for x in item]
        elif isinstance(item, ObjectId):
            return str(item)
        return item

    doc = stringify_objectids(doc)
    doc["_id"] = str(doc["_id"])
    
    # Ensure every returned document has an 'id' field compatible with frontend expectations
    if "id" not in doc:
        if col_name == "jobs" and "job_id" in doc:
            doc["id"] = doc["job_id"]
        elif col_name == "applications" and "application_id" in doc:
            doc["id"] = doc["application_id"]
        elif col_name == "cvs" and "cv_id" in doc:
            doc["id"] = doc["cv_id"]
        elif col_name == "notifications" and "notification_id" in doc:
            doc["id"] = doc["notification_id"]
        else:
            doc["id"] = doc["_id"]
            
    # Keep both forms of the ID fields for double-sided compatibility
    if col_name == "jobs" and "job_id" not in doc:
        doc["job_id"] = doc["id"]
    elif col_name == "applications" and "application_id" not in doc:
        doc["application_id"] = doc["id"]
        
    return doc

@router.get("/{collection}/")
async def list_entities(collection: str, request: Request):
    col_name = get_collection_name(collection)
    col = db[col_name]
    
    # Parse query parameters as filters
    query_params = dict(request.query_params)
    filter_query = {}
    
    for k, v in query_params.items():
        if v.lower() == "true":
            filter_query[k] = True
        elif v.lower() == "false":
            filter_query[k] = False
        else:
            filter_query[k] = v
            
    # Exclude text index fields from listing unless explicitly queried to optimize performance
    projection = {}
    if col_name in ["jobs", "applications", "candidates"]:
        # We can fetch everything but limit length to make it fast
        pass
        
    docs = await col.find(filter_query, projection).to_list(length=1000)
    
    # Resolve candidate names from profile if not correctly set
    if col_name == "applications":
        for doc in docs:
            c_name = doc.get("candidate_name")
            c_email = doc.get("candidate_email")
            if not c_name or c_name == "Unknown" or c_name == c_email or "@" in str(c_name):
                if c_email:
                    cand = await db["candidates"].find_one({"email": c_email.strip().lower()})
                    if not cand:
                        cand = await db["users"].find_one({"email": c_email.strip().lower()})
                    if cand:
                        doc["candidate_name"] = cand.get("full_name") or cand.get("name") or c_name

    
    # Smart sorting: default to sorting by created_date or created_at descending if fields exist
    def get_sort_key(d):
        val = d.get("created_date") or d.get("created_at") or d.get("cv_uploaded_at")
        if not val:
            return ""
        return str(val)
        
    docs.sort(key=get_sort_key, reverse=True)
    
    return [format_doc(d, col_name) for d in docs]

@router.get("/candidate/{id_or_email}/full-profile")
async def get_candidate_full_profile(id_or_email: str, job_id: str = None):
    # Try looking up by email, id, user_id, or ObjectId
    candidate = await db["candidates"].find_one({"email": id_or_email.strip().lower()})
    if not candidate:
        candidate = await db["candidates"].find_one({"$or": [{"id": id_or_email}, {"user_id": id_or_email}]})
    if not candidate:
        try:
            candidate = await db["candidates"].find_one({"_id": ObjectId(id_or_email)})
        except:
            pass
            
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")
        
    # Get psychometric test result
    psychometric = await db["assessment_results"].find_one(
        {"candidate_email": candidate["email"]},
        sort=[("created_date", -1)]
    )
    
    # Get application info if job_id is provided
    application_data = None
    if job_id:
        app = await db["applications"].find_one({
            "candidate_email": candidate["email"],
            "job_id": job_id
        })
        if app:
            app_formatted = format_doc(app, "applications")
            application_data = {
                "match_score": app_formatted.get("match_score"),
                "status": app_formatted.get("status"),
                "applied_date": app_formatted.get("upload_date") or app_formatted.get("created_date") or app_formatted.get("created_at"),
                "feedback": app_formatted.get("feedback")
            }
            
    candidate_data = format_doc(candidate, "candidates")
    psych_data = format_doc(psychometric, "assessments") if psychometric else None
    
    return {
        "candidate": {
            "id": candidate_data.get("id"),
            "name": candidate_data.get("full_name"),
            "email": candidate_data.get("email"),
            "phone": candidate_data.get("phone"),
            "created_date": candidate_data.get("created_date")
        },
        "psychometric": {
            "completed": psych_data is not None,
            "completed_date": psych_data.get("created_date") if psych_data else None,
            "scores": {
                "openness": psych_data.get("score_openness") if psych_data else None,
                "conscientiousness": psych_data.get("score_conscientiousness") if psych_data else None,
                "extraversion": psych_data.get("score_extraversion") if psych_data else None,
                "agreeableness": psych_data.get("score_agreeableness") if psych_data else None,
                "stability": psych_data.get("score_stability") or psych_data.get("score_neuroticism") if psych_data else None
            } if psych_data else None,
            "recommended_jobs": psych_data.get("recommended_jobs") if psych_data else None,
            "recommended_reason": psych_data.get("recommended_reason") if psych_data else None
        },
        "cv": {
            "url": candidate_data.get("cv_url"),
            "filename": candidate_data.get("cv_filename"),
            "uploaded_date": candidate_data.get("cv_uploaded_at"),
            "skills": candidate_data.get("skills") or []
        },
        "application": application_data
    }

@router.get("/recruiter/profile")
async def get_recruiter_profile(current_user: dict = Depends(get_user_by_token)):
    if current_user.get("role") != "recruiter":
        raise HTTPException(status_code=403, detail="Forbidden: user is not a recruiter")
    rec_profile = await db["recruiters"].find_one({"user_id": current_user["id"]})
    if not rec_profile:
        rec_profile = await db["recruiters"].find_one({"email": current_user["email"]})
    if not rec_profile:
        raise HTTPException(status_code=404, detail="Recruiter profile not found")
    return format_doc(rec_profile, "recruiters")

@router.put("/recruiter/profile")
async def update_recruiter_profile(data: dict, current_user: dict = Depends(get_user_by_token)):
    if current_user.get("role") != "recruiter":
        raise HTTPException(status_code=403, detail="Forbidden: user is not a recruiter")
    
    rec_profile = await db["recruiters"].find_one({"user_id": current_user["id"]})
    if not rec_profile:
        rec_profile = await db["recruiters"].find_one({"email": current_user["email"]})
    if not rec_profile:
        raise HTTPException(status_code=404, detail="Recruiter profile not found")
    
    cleaned_data = {k: v for k, v in data.items() if k not in ["id", "_id", "user_id", "email", "company", "company_name", "created_date"]}
    
    await db["recruiters"].update_one({"id": rec_profile["id"]}, {"$set": cleaned_data})
    
    user_update = {}
    if "company_website" in cleaned_data:
        user_update["company_website"] = cleaned_data["company_website"]
    if "company_overview" in cleaned_data:
        user_update["company_overview"] = cleaned_data["company_overview"]
    if "full_name" in cleaned_data:
        user_update["full_name"] = cleaned_data["full_name"]
    if user_update:
        await db["users"].update_one({"id": current_user["id"]}, {"$set": user_update})
        
    updated = await db["recruiters"].find_one({"id": rec_profile["id"]})
    return format_doc(updated, "recruiters")

class StatusWithFeedbackRequest(BaseModel):
    status: str

@router.put("/applications/{id}/status-with-feedback")
async def update_application_status_with_feedback(id: str, req: StatusWithFeedbackRequest):
    application_col = db["applications"]
    app = await application_col.find_one({"$or": [{"id": id}, {"application_id": id}]})
    if not app:
        try:
            app = await application_col.find_one({"_id": ObjectId(id)})
        except:
            pass
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    old_status = app.get("status")
    new_status = req.status.lower().strip()
    
    job_id = app.get("job_id")
    job = await db["jobs"].find_one({"$or": [{"id": job_id}, {"job_id": job_id}]})
    if not job:
        job = {"title": app.get("job_title") or "Position", "company": "Company"}
        
    def format_skills(skills):
        if not skills:
            return "your field"
        skills = [s.strip() for s in skills if s and s.strip()]
        if not skills:
            return "your field"
        if len(skills) == 1:
            return skills[0]
        elif len(skills) == 2:
            return f"{skills[0]} and {skills[1]}"
        else:
            first_part = ", ".join(skills[:2])
            return f"{first_part}, and {skills[2]}"
            
    skills_list = []
    c_email = app.get("candidate_email")
    if c_email:
        cand = await db["candidates"].find_one({"email": c_email.strip().lower()})
        if cand:
            skills_list = cand.get("skills") or cand.get("extracted_skills") or []
    if not skills_list:
        skills_list = app.get("skills") or app.get("extracted_skills") or []
        
    if new_status == "shortlisted":
        skills_str = format_skills(skills_list)
        feedback = f"Congratulations! Your application for {job['title']} has been shortlisted. Your skills in {skills_str} align well with our requirements. Our team will contact you shortly with next steps."
    elif new_status == "rejected":
        feedback = f"Thank you for your application for {job['title']}. While your background is impressive, we have decided to move forward with other candidates whose experience more closely matches our needs. We wish you the best in your job search."
    else:
        feedback = f"Your application for {job['title']} is currently under review. We will notify you once a decision has been made."
        
    await application_col.update_one(
        {"_id": app["_id"]},
        {"$set": {
            "status": req.status,
            "feedback": feedback
        }}
    )
    
    if req.status in ["shortlisted", "rejected"] and old_status != req.status:
        candidate_id = app.get("candidate_id")
        if not candidate_id:
            cand_email = app.get("candidate_email")
            if cand_email:
                cand_email_clean = cand_email.strip().lower()
                cand = await db["candidates"].find_one({"email": cand_email_clean})
                candidate_id = cand.get("user_id") if cand else None
                if not candidate_id:
                    user_doc = await db["users"].find_one({"email": cand_email_clean})
                    if user_doc:
                        candidate_id = str(user_doc.get("id"))
            candidate_id = candidate_id or "unknown_candidate"
            
        notif_id = f"notif_{uuid.uuid4().hex[:8]}"
        notification = {
            "id": notif_id,
            "notification_id": notif_id,
            "candidate_id": candidate_id,
            "application_id": app.get("id") or str(app.get("_id")),
            "job_title": job["title"],
            "company_name": job.get("company", "Company"),
            "status": req.status,
            "message": f"Your application for {job['title']} has been {req.status}.",
            "read": False,
            "created_date": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc)
        }
        await db["notifications"].insert_one(notification)
        
    updated = await application_col.find_one({"_id": app["_id"]})
    return format_doc(updated, "applications")

@router.get("/{collection}/{id}")
async def get_entity(collection: str, id: str):
    col_name = get_collection_name(collection)
    col = db[col_name]
    
    # Try looking up by id, job_id, application_id, or MongoDB ObjectId
    query = {"$or": [
        {"id": id},
        {"job_id": id},
        {"application_id": id},
        {"cv_id": id}
    ]}
    
    doc = await col.find_one(query)
    if not doc:
        try:
            doc = await col.find_one({"_id": ObjectId(id)})
        except:
            pass
            
    if not doc:
        raise HTTPException(status_code=404, detail=f"{collection} with id {id} not found")
        
    return format_doc(doc, col_name)

@router.post("/{collection}/")
async def create_entity(collection: str, data: dict):
    col_name = get_collection_name(collection)
    col = db[col_name]
    
    # Ensure user_id/id formatting is properly populated
    if "id" not in data:
        prefix = {
            "jobs": "jd",
            "applications": "app",
            "candidates": "cand",
            "recruiters": "rec",
            "interview_slots": "slot",
            "assessments": "asmt",
            "psych_questions": "q",
            "notifications": "notif"
        }.get(col_name, "item")
        data["id"] = f"{prefix}_{uuid.uuid4().hex[:8]}"
        
    # Standard created timestamps
    if "created_date" not in data:
        data["created_date"] = datetime.utcnow().isoformat()
        
    # Maintain backward compatibility identifiers
    if col_name == "jobs" and "job_id" not in data:
        data["job_id"] = data["id"]
    elif col_name == "applications" and "application_id" not in data:
        data["application_id"] = data["id"]
    elif col_name == "notifications" and "notification_id" not in data:
        data["notification_id"] = data["id"]
        
    if col_name == "jobs" and "status" not in data:
        data["status"] = "open"
        
    await col.insert_one(data)
    
    inserted = await col.find_one({"id": data["id"]})
    return format_doc(inserted, col_name)

@router.put("/{collection}/{id}")
async def update_entity(collection: str, id: str, data: dict):
    col_name = get_collection_name(collection)
    col = db[col_name]
    
    # Never update the primary _id
    data.pop("_id", None)
    
    # Silently ignore updates to immutable fields for recruiters
    if col_name == "recruiters":
        data.pop("email", None)
        data.pop("company", None)
        data.pop("company_name", None)
    
    query = {"$or": [
        {"id": id},
        {"job_id": id},
        {"application_id": id},
        {"cv_id": id}
    ]}
    
    # Intercept application updates to generate notifications or fresh AI feedback
    if col_name == "applications":
        old_app = await col.find_one(query)
        if not old_app:
            try:
                old_app = await col.find_one({"_id": ObjectId(id)})
            except:
                pass
                
        if old_app:
            # 1. Intercept status changes to generate notifications for candidates
            if "status" in data:
                new_status = data["status"]
                if new_status in ["shortlisted", "rejected"] and old_app.get("status") != new_status:
                    application = old_app
                    application_id = old_app.get("id") or str(old_app.get("_id"))
                    status = new_status
                    
                    # Robustly resolve candidate_id to prevent KeyError
                    if "candidate_id" not in application or not application["candidate_id"]:
                        cand_email = application.get("candidate_email")
                        candidate_id = None
                        if cand_email:
                            cand_email_clean = cand_email.strip().lower()
                            cand = await db["candidates"].find_one({"email": cand_email_clean})
                            candidate_id = cand.get("user_id") if cand else None
                            if not candidate_id:
                                user_doc = await db["users"].find_one({"email": cand_email_clean})
                                if user_doc:
                                    candidate_id = str(user_doc.get("id"))
                        application["candidate_id"] = candidate_id or "unknown_candidate"
                    
                    # Robustly resolve job to prevent TypeError
                    job_id = application.get("job_id")
                    job = await db["jobs"].find_one({"$or": [{"id": job_id}, {"job_id": job_id}]})
                    if not job:
                        job = {"title": application.get("job_title") or "Position", "company": "Company"}
                    
                    notif_id = f"notif_{uuid.uuid4().hex[:8]}"
                    notification = {
                        "id": notif_id,
                        "notification_id": notif_id,
                        "candidate_id": application["candidate_id"],
                        "application_id": application_id,
                        "job_title": job["title"],
                        "company_name": job.get("company", "Company"),
                        "status": status,  # "shortlisted" or "rejected"
                        "message": f"Your application for {job['title']} has been {status}.",
                        "read": False,
                        "created_date": datetime.now(timezone.utc),
                        "created_at": datetime.now(timezone.utc)
                    }
                    await db["notifications"].insert_one(notification)

            # 2. Intercept match_score changes to generate fresh AI feedback
            if "match_score" in data:
                # Fetch job details
                job_id = data.get("job_id") or old_app.get("job_id")
                job = None
                if job_id:
                    job = await db["jobs"].find_one({"$or": [{"id": job_id}, {"job_id": job_id}]})
                
                # Fetch CV text
                cv_url = data.get("cv_url") or old_app.get("cv_url")
                cv_text = ""
                if cv_url:
                    from urllib.parse import urlparse
                    import os
                    from config import UPLOAD_DIR
                    from routes.match import extract_text_from_path
                    
                    parsed_url = urlparse(cv_url)
                    filename = os.path.basename(parsed_url.path)
                    local_path = os.path.join(UPLOAD_DIR, filename)
                    if os.path.exists(local_path):
                        cv_text = extract_text_from_path(local_path)
                
                if not cv_text:
                    cv_text = f"Resume of {old_app.get('candidate_name', 'Candidate')}. Skills: {', '.join(old_app.get('skills', [])) or 'Development'}."
                
                from services.matcher import generate_candidate_feedback
                feedback_text = await generate_candidate_feedback(
                    match_score=data["match_score"],
                    job_title=job["title"] if job else (old_app.get("job_title") or "Position"),
                    job_description=job["description"] if job else "",
                    cv_summary=cv_text
                )
                data["feedback"] = feedback_text
                    
    # Perform update in database
    result = await col.update_one(query, {"$set": data})
    if result.matched_count == 0:
        try:
            await col.update_one({"_id": ObjectId(id)}, {"$set": data})
        except:
            pass
            
    # Sync relevant recruiter changes (like company_website) to the users collection
    if col_name == "recruiters":
        rec_doc = await col.find_one(query)
        if rec_doc:
            user_id = rec_doc.get("user_id")
            if user_id:
                user_update = {}
                if "company_website" in data:
                    user_update["company_website"] = data["company_website"]
                if "company_overview" in data:
                    user_update["company_overview"] = data["company_overview"]
                if "full_name" in data:
                    user_update["full_name"] = data["full_name"]
                if user_update:
                    await db["users"].update_one({"id": user_id}, {"$set": user_update})
            
    # Fetch updated document
    updated = await col.find_one(query)
    if not updated:
        try:
            updated = await col.find_one({"_id": ObjectId(id)})
        except:
            pass
            
    if not updated:
        raise HTTPException(status_code=404, detail=f"{collection} with id {id} not found")
        
    return format_doc(updated, col_name)

@router.delete("/{collection}/{id}")
async def delete_entity(collection: str, id: str):
    col_name = get_collection_name(collection)
    col = db[col_name]
    
    query = {"$or": [
        {"id": id},
        {"job_id": id},
        {"application_id": id},
        {"cv_id": id}
    ]}
    
    result = await col.delete_one(query)
    if result.deleted_count == 0:
        try:
            result = await col.delete_one({"_id": ObjectId(id)})
        except:
            pass
            
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"{collection} with id {id} not found")
        
    return {"message": f"Deleted {collection} with id: {id}"}

@router.get("/applications/job/{job_id}")
async def get_applications_by_job(job_id: str, user: dict = Depends(get_user_by_token)):
    # 1. Fetch the job details to verify ownership
    job = await db["jobs"].find_one({"$or": [{"id": job_id}, {"job_id": job_id}]})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # 2. Check recruiter ownership
    role = user.get("role")
    if role not in ["recruiter", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to view applications")
        
    if role == "recruiter":
        is_owner = (
            job.get("recruiter_id") == user["id"] or 
            job.get("created_by") == user["id"] or 
            job.get("recruiter_email") == user["email"]
        )
        if not is_owner:
            raise HTTPException(status_code=403, detail="You do not have access to this job's applications")
            
    # 3. Fetch applications for this job
    apps = await db["applications"].find({"job_id": job_id}).to_list(length=1000)
    
    # 4. Format and return details
    formatted_apps = []
    for app in apps:
        cv_url = app.get("cv_url", "")
        cv_filename = cv_url.split("/")[-1] if cv_url else "—"
        
        c_name = app.get("candidate_name")
        c_email = app.get("candidate_email")
        if not c_name or c_name == "Unknown" or c_name == c_email or "@" in str(c_name):
            if c_email:
                cand = await db["candidates"].find_one({"email": c_email.strip().lower()})
                if not cand:
                    cand = await db["users"].find_one({"email": c_email.strip().lower()})
                if cand:
                    c_name = cand.get("full_name") or cand.get("name") or c_name

        formatted_apps.append({
            "id": app.get("id") or str(app.get("_id")),
            "candidate_name": c_name or "Unknown",
            "candidate_email": c_email or "—",
            "cv_url": cv_url,
            "cv_filename": cv_filename,
            "upload_date": app.get("created_date") or app.get("created_at") or "—",
            "match_score": app.get("match_score"),
            "status": app.get("status") or "pending",
            "feedback": app.get("feedback"),
            "rag_results": app.get("rag_results")
        })
        
    return formatted_apps

@router.get("/applications/{id}/feedback")
async def get_application_feedback(id: str, user: dict = Depends(get_user_by_token)):
    app = await db["applications"].find_one({"id": id})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if user.get("role") == "candidate" and app.get("candidate_email") != user.get("email"):
        raise HTTPException(status_code=403, detail="Not authorized to view this feedback")
        
    return {"feedback": app.get("feedback") or ""}

