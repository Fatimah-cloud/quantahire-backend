import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from config import UPLOAD_DIR

router = APIRouter(prefix="/api/upload", tags=["Uploads"])

@router.post("/")
async def upload_file(file: UploadFile = File(...)):
    """
    Saves a multipart file upload to the UPLOAD_DIR and returns its public URL.
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # Save the file with a unique prefix to avoid filename collisions
    unique_prefix = uuid.uuid4().hex[:8]
    sanitized_filename = f"{unique_prefix}_{file.filename.replace(' ', '_')}"
    dest_path = os.path.join(UPLOAD_DIR, sanitized_filename)
    
    try:
        content = await file.read()
        with open(dest_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
    # Return the direct accessible URL
    # Assuming the server is running on http://localhost:8000
    file_url = f"http://localhost:8000/uploads/{sanitized_filename}"
    
    return {
        "message": "File uploaded successfully",
        "filename": sanitized_filename,
        "original_filename": file.filename,
        "file_url": file_url
    }
