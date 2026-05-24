import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional
from db.mongo import db

router = APIRouter(prefix="/api/auth", tags=["Auth"])

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str # "recruiter" or "candidate" or "admin"
    company: Optional[str] = None
    certificate_url: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

async def get_user_by_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.split(" ")[1]
    # In our simple mock auth system, the token is the user_id
    user = await db["users"].find_one({"id": token}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session or token")
    return user

@router.post("/register")
async def register(req: RegisterRequest):
    email_lower = req.email.strip().lower()
    
    # Check if user already exists
    existing = await db["users"].find_one({"email": email_lower})
    if existing:
        return {"error": "An account with this email already exists."}
        
    user_id = f"usr_{uuid.uuid4().hex[:8]}"
    created_at = datetime.utcnow().isoformat()
    
    # Recruiters need admin approval, candidates and admins are active immediately
    is_active = False if req.role == "recruiter" else True
    
    user_doc = {
        "id": user_id,
        "email": email_lower,
        "password": req.password, # storing plain for local dev compatibility
        "role": req.role,
        "full_name": req.full_name,
        "is_active": is_active,
        "created_date": created_at
    }
    
    await db["users"].insert_one(user_doc)
    
    # Also create recruiter or candidate profile record
    if req.role == "recruiter":
        profile_id = f"rec_{uuid.uuid4().hex[:8]}"
        profile = {
            "id": profile_id,
            "user_id": user_id,
            "email": email_lower,
            "full_name": req.full_name,
            "company": req.company or "",
            "certificate_url": req.certificate_url or "",
            "status": "pending",
            "created_date": created_at
        }
        await db["recruiters"].insert_one(profile)
        
    elif req.role == "candidate":
        profile_id = f"cand_{uuid.uuid4().hex[:8]}"
        profile = {
            "id": profile_id,
            "user_id": user_id,
            "email": email_lower,
            "full_name": req.full_name,
            "created_date": created_at,
            "total_applications": 0,
            "accepted_count": 0,
            "rejected_count": 0
        }
        await db["candidates"].insert_one(profile)
        
    return {
        "message": "Registration successful",
        "user": {
            "id": user_id,
            "email": email_lower,
            "role": req.role,
            "full_name": req.full_name,
            "is_active": is_active
        }
    }

@router.post("/login")
async def login(req: LoginRequest):
    email_lower = req.email.strip().lower()
    
    try:
        user = await db["users"].find_one({"email": email_lower})
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Database connection failed. Please ensure your IP address is whitelisted in your MongoDB Atlas dashboard (Security > Network Access) and that you are not behind a VPN/firewall."
        )
    if not user:
        return {"error": "No account found for this email. Please register first or contact your admin."}
        
    if user["password"] != req.password:
        return {"error": "Invalid email or password."}
        
    # Check recruiter status
    if user["role"] == "recruiter":
        profile = await db["recruiters"].find_one({"email": email_lower})
        if profile:
            status = profile.get("status", "pending")
            if status == "pending":
                return {"error": "Your account is still pending admin approval. You will be notified by email once approved."}
            elif status == "blocked" or status == "suspended":
                return {"error": "Your account has been blocked or suspended. Please contact support."}
            elif status == "denied":
                return {"error": "You don't have access to the recruiter portal."}
                
    return {
        "token": user["id"],
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "full_name": user["full_name"],
            "is_active": user["is_active"]
        }
    }

@router.get("/me")
async def get_me(user: dict = Depends(get_user_by_token)):
    return user
