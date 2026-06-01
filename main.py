from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional
import os
from config import UPLOAD_DIR
from routes import cvs, jobs, match, auth, entities, upload, psych
from db.mongo import db

app = FastAPI(title="QuantaHire API", version="1.0.0")

# Allow your frontend (QuantaHire / Antigravity) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # replace * with your frontend URL in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(cvs.router)
from routes.cvs import candidate_cv_router
app.include_router(candidate_cv_router)
app.include_router(jobs.router)
app.include_router(match.router)
from routes import notifications
app.include_router(notifications.router)
app.include_router(psych.router)
app.include_router(entities.router)


@app.get("/uploads/{filename}")
async def serve_upload_file(
    filename: str,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = None
):
    """
    Serves files from uploads/ folder, adding logging to show requested file ID/name,
    its existence on disk/DB, and the user's permission level.
    """
    # 1. Check user permission level
    user = None
    auth_token = None
    if authorization and authorization.startswith("Bearer "):
        auth_token = authorization.split(" ")[1]
    elif token:
        auth_token = token

    if auth_token:
        user = await db["users"].find_one({"id": auth_token}, {"_id": 0})

    user_permission = user.get("role") if user else "Anonymous (No Auth Token)"
    user_email = user.get("email") if user else "Anonymous"

    # 2. Storage existence check
    target_path = os.path.join(UPLOAD_DIR, filename)
    file_exists_on_disk = os.path.exists(target_path)

    # 3. Database existence check
    # Check in cvs collection first
    cv_record = await db["cvs"].find_one({"filename": filename})
    db_exists = cv_record is not None
    record_source = "cvs collection"

    if not db_exists:
        # Check in applications collection where cv_url ends with filename
        app_record = await db["applications"].find_one({"cv_url": {"$regex": filename + "$"}})
        if app_record:
            db_exists = True
            record_source = "applications collection"
        else:
            # Check in recruiters collection (for recruiter certificates)
            rec_record = await db["recruiters"].find_one({"certificate_url": {"$regex": filename + "$"}})
            if rec_record:
                db_exists = True
                record_source = "recruiters collection"

    # 4. Detailed Logging
    print("\n" + "="*60)
    print("DEBUG LOG: STATIC UPLOADS ACCESS REQUEST")
    print(f"Requested File Name: {filename}")
    print(f"Target Path: {target_path}")
    print(f"Exists in Database: {db_exists} ({record_source if db_exists else 'Not found in DB'})")
    print(f"Exists on Disk: {file_exists_on_disk}")
    print(f"Requester Email: {user_email}")
    print(f"Requester Role/Permission Level: {user_permission}")
    print("="*60 + "\n")

    if not file_exists_on_disk:
        # Starlette's StaticFiles returns a 404 detail Not Found, let's match it
        raise HTTPException(status_code=404, detail="Not Found")

    return FileResponse(target_path)


# Mount static uploads directory
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.get("/")
async def root():
    return {"message": "QuantaHire API is running ✅"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.on_event("startup")
async def startup_db_client():
    # Update any jobs in the jobs collection that don't have a status field, setting it to "open"
    try:
        await db["jobs"].update_many({"status": {"$exists": False}}, {"$set": {"status": "open"}})
    except Exception as e:
        print(f"Startup migration failed: {e}")

    # Seed psychometric questions if the collection is empty
    try:
        from routes.psych import run_seed
        psych_col = db["psych_questions"]
        count = await psych_col.count_documents({})
        has_old = await psych_col.find_one({"trait": "stability"})
        if count == 0 or has_old:
            await run_seed()
            print("Successfully seeded 10 psychometric questions ✅")
    except Exception as e:
        print(f"Psychometric questions seeding failed: {e}")


