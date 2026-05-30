import uuid
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from db.mongo import db
from bson import ObjectId

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
        "assessments": "assessments",
        "psych_questions": "psych_questions"
    }
    return mapping.get(name, name)

def format_doc(doc: dict, col_name: str) -> dict:
    if not doc:
        return doc
    doc["_id"] = str(doc["_id"])
    
    # Ensure every returned document has an 'id' field compatible with frontend expectations
    if "id" not in doc:
        if col_name == "jobs" and "job_id" in doc:
            doc["id"] = doc["job_id"]
        elif col_name == "applications" and "application_id" in doc:
            doc["id"] = doc["application_id"]
        elif col_name == "cvs" and "cv_id" in doc:
            doc["id"] = doc["cv_id"]
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
    
    # Smart sorting: default to sorting by created_date or created_at descending if fields exist
    def get_sort_key(d):
        val = d.get("created_date") or d.get("created_at") or d.get("cv_uploaded_at")
        if not val:
            return ""
        return str(val)
        
    docs.sort(key=get_sort_key, reverse=True)
    
    return [format_doc(d, col_name) for d in docs]

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
            "psych_questions": "q"
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
    
    query = {"$or": [
        {"id": id},
        {"job_id": id},
        {"application_id": id},
        {"cv_id": id}
    ]}
    
    # Perform update in database
    result = await col.update_one(query, {"$set": data})
    if result.matched_count == 0:
        try:
            await col.update_one({"_id": ObjectId(id)}, {"$set": data})
        except:
            pass
            
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
