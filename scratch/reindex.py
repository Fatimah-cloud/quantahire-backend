import asyncio
import os
os.environ["FLAGS_use_onednn"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
import sys

# Add project root to sys.path so we can import db and services correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.mongo import cvs_col
from services.matcher import rag

def safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        try:
            sys.stdout.buffer.write((msg + "\n").encode('utf-8', errors='replace'))
            sys.stdout.flush()
        except:
            try:
                print(msg.encode('ascii', errors='ignore').decode('ascii'))
            except:
                pass

async def reindex_all():
    safe_print("🚀 Starting retroactive RAG/Knowledge Graph indexing for all existing resumes...")
    
    cvs = []
    try:
        cvs = await cvs_col.find({}).to_list(length=1000)
        safe_print(f"📋 Found {len(cvs)} CV record(s) in MongoDB cvs collection.")
    except Exception as mongo_err:
        safe_print(f"\n⚠️  [MongoDB Error] Failed to connect or retrieve from MongoDB: {mongo_err}")
        safe_print("💡 TIP: If you are using MongoDB Atlas, this is likely because your current IP address is not whitelisted.")
        safe_print("📁 Falling back to scanning the local 'uploads' directory for files to index...\n")
        
        uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
        if os.path.exists(uploads_dir):
            import glob
            files = glob.glob(os.path.join(uploads_dir, "*.pdf")) + glob.glob(os.path.join(uploads_dir, "*.docx"))
            safe_print(f"📁 Found {len(files)} resume file(s) in local uploads directory: {uploads_dir}")
            for f in files:
                cvs.append({
                    "cv_id": os.path.splitext(os.path.basename(f))[0],
                    "path": f,
                    "original_filename": os.path.basename(f)
                })
        else:
            safe_print(f"❌ Local 'uploads' directory does not exist at: {uploads_dir}")
            return

    indexed_count = 0
    failed_count = 0
    
    for cv in cvs:
        cv_id = cv.get("cv_id")
        path = cv.get("path")
        original_name = cv.get("original_filename", cv_id)
        
        if not path:
            safe_print(f"⚠️  Missing file path for candidate: {cv_id}")
            failed_count += 1
            continue
            
        if not os.path.exists(path):
            adjusted_path = path.replace("/quantahire-backend/", "/quantahire-backend-main/")
            if os.path.exists(adjusted_path):
                path = adjusted_path
            else:
                safe_print(f"❌ Resume file not found: {original_name} ({cv_id})")
                failed_count += 1
                continue
        
        try:
            safe_print(f"🔍 Indexing resume: {original_name} ({cv_id})")
            await rag.process_document_complete(path)
            safe_print(f"✅ Successfully indexed: {cv_id}")
            indexed_count += 1
        except Exception as e:
            safe_print(f"❌ Failed to index {cv_id}: {e}")
            failed_count += 1
            
    safe_print(f"\n🎉 Indexing complete!")
    safe_print(f"   - Successfully indexed: {indexed_count}")
    safe_print(f"   - Failed/Skipped: {failed_count}")

if __name__ == "__main__":
    asyncio.run(reindex_all())
