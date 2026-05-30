from fastapi import APIRouter, HTTPException, Depends
from db.mongo import db
from routes.auth import get_user_by_token

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

@router.get("")
async def get_notifications(user: dict = Depends(get_user_by_token)):
    if user.get("role") != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can fetch notifications")
    
    notifications = await db["notifications"].find({"candidate_id": user["id"]}).to_list(length=1000)
    for n in notifications:
        n["_id"] = str(n["_id"])
        if "id" not in n:
            n["id"] = n.get("notification_id") or str(n["_id"])
    return notifications

@router.get("/unread/count")
async def get_unread_count(user: dict = Depends(get_user_by_token)):
    if user.get("role") != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can fetch notifications")
        
    count = await db["notifications"].count_documents({"candidate_id": user["id"], "read": False})
    return {"count": count}

@router.put("/{id}/read")
async def mark_as_read(id: str, user: dict = Depends(get_user_by_token)):
    if user.get("role") != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can modify notifications")
        
    query = {"$or": [{"id": id}, {"notification_id": id}]}
    query["candidate_id"] = user["id"]
    
    result = await db["notifications"].update_one(query, {"$set": {"read": True}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    updated = await db["notifications"].find_one(query)
    updated["_id"] = str(updated["_id"])
    if "id" not in updated:
        updated["id"] = updated.get("notification_id") or str(updated["_id"])
    return updated
