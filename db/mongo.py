from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, MONGO_DB

client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db     = client[MONGO_DB]

# Collections
jobs_col    = db["jobs"]       # job descriptions
cvs_col     = db["cvs"]        # uploaded CVs + extracted text
results_col = db["results"]    # matching results per job
sessions_col = db["sessions"]  # human-in-the-loop session state
