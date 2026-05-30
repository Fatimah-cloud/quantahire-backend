from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from config import UPLOAD_DIR
from routes import cvs, jobs, match, auth, entities, upload
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
        psych_col = db["psych_questions"]
        count = await psych_col.count_documents({})
        if count == 0:
            questions = [
                {
                    "id": "q_1",
                    "order_index": 1,
                    "trait": "extraversion",
                    "text": "I see myself as extraverted, enthusiastic.",
                    "is_reverse_scored": False
                },
                {
                    "id": "q_2",
                    "order_index": 2,
                    "trait": "agreeableness",
                    "text": "I see myself as critical, quarrelsome.",
                    "is_reverse_scored": True
                },
                {
                    "id": "q_3",
                    "order_index": 3,
                    "trait": "conscientiousness",
                    "text": "I see myself as dependable, self-disciplined.",
                    "is_reverse_scored": False
                },
                {
                    "id": "q_4",
                    "order_index": 4,
                    "trait": "stability",
                    "text": "I see myself as anxious, easily upset.",
                    "is_reverse_scored": True
                },
                {
                    "id": "q_5",
                    "order_index": 5,
                    "trait": "openness",
                    "text": "I see myself as open to new experiences, complex.",
                    "is_reverse_scored": False
                },
                {
                    "id": "q_6",
                    "order_index": 6,
                    "trait": "extraversion",
                    "text": "I see myself as reserved, quiet.",
                    "is_reverse_scored": True
                },
                {
                    "id": "q_7",
                    "order_index": 7,
                    "trait": "agreeableness",
                    "text": "I see myself as sympathetic, warm.",
                    "is_reverse_scored": False
                },
                {
                    "id": "q_8",
                    "order_index": 8,
                    "trait": "conscientiousness",
                    "text": "I see myself as disorganized, careless.",
                    "is_reverse_scored": True
                },
                {
                    "id": "q_9",
                    "order_index": 9,
                    "trait": "stability",
                    "text": "I see myself as calm, emotionally stable.",
                    "is_reverse_scored": False
                },
                {
                    "id": "q_10",
                    "order_index": 10,
                    "trait": "openness",
                    "text": "I see myself as conventional, uncreative.",
                    "is_reverse_scored": True
                }
            ]
            await psych_col.insert_many(questions)
            print("Successfully seeded 10 psychometric questions ✅")
    except Exception as e:
        print(f"Psychometric questions seeding failed: {e}")


