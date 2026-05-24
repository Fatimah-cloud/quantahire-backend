from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from config import UPLOAD_DIR
from routes import cvs, jobs, match, auth, entities, upload

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
app.include_router(entities.router)
app.include_router(upload.router)
app.include_router(cvs.router)
app.include_router(jobs.router)
app.include_router(match.router)

# Mount static uploads directory
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.get("/")
async def root():
    return {"message": "QuantaHire API is running ✅"}

@app.get("/health")
async def health():
    return {"status": "ok"}

