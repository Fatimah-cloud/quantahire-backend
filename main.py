from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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


