import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Header
from typing import Optional
from config import UPLOAD_DIR
from db.mongo import db, cvs_col
from datetime import datetime
import fitz  # PyMuPDF
import docx as docx_lib

router = APIRouter(prefix="/api/upload", tags=["Uploads"])

def extract_text(path: str) -> str:
    """Extracts text from PDF and DOCX files."""
    if path.endswith(".docx"):
        try:
            doc = docx_lib.Document(path)
            text = " ".join(p.text for p in doc.paragraphs)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        text += " " + cell.text
            return text
        except Exception as e:
            print("Docx extract error in upload route:", e)
            return ""
    elif path.endswith(".pdf"):
        try:
            doc = fitz.open(path)
            text = " ".join(page.get_text() for page in doc)
            doc.close()
            return text
        except Exception as e:
            print("PDF extract error in upload route:", e)
            return ""
    return ""

@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None)
):
    """
    Saves a multipart file upload to the UPLOAD_DIR and returns its public URL.
    If a candidate user ID is provided, registers the CV in MongoDB cvs collection and candidates profile.
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # Resolve user_id from Authorization header if not supplied in form
    resolved_user_id = user_id
    if not resolved_user_id and authorization and authorization.startswith("Bearer "):
        resolved_user_id = authorization.split(" ")[1]
        
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
    file_url = f"http://localhost:8000/uploads/{sanitized_filename}"
    
    # Process CV text extraction and update MongoDB if candidate is registered
    if resolved_user_id:
        extracted_text = ""
        filename_lower = file.filename.lower()
        if filename_lower.endswith((".pdf", ".docx")):
            extracted_text = extract_text(dest_path)
            
        cv_id = f"cv_{uuid.uuid4().hex[:8]}"
        cv_data = {
            "cv_id": cv_id,
            "user_id": resolved_user_id,
            "original_filename": file.filename,
            "filename": sanitized_filename,
            "file_url": file_url,
            "path": dest_path,
            "text": extracted_text,
            "category": "General",
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Save/Upsert in MongoDB 'cvs' collection
        await cvs_col.update_one(
            {"user_id": resolved_user_id},
            {"$set": cv_data},
            upsert=True
        )
        
        # Update corresponding Candidate profile in 'candidates' collection
        candidate = await db["candidates"].find_one({"user_id": resolved_user_id})
        if candidate:
            await db["candidates"].update_one(
                {"user_id": resolved_user_id},
                {"$set": {
                    "cv_url": file_url,
                    "cv_filename": file.filename,
                    "cv_uploaded_at": datetime.utcnow().isoformat()
                }}
            )
        else:
            # Fallback to update by user's email if user_id field isn't populated on candidate
            user = await db["users"].find_one({"id": resolved_user_id})
            if user:
                email_lower = user.get("email", "").strip().lower()
                if email_lower:
                    await db["candidates"].update_one(
                        {"email": email_lower},
                        {"$set": {
                            "cv_url": file_url,
                            "cv_filename": file.filename,
                            "cv_uploaded_at": datetime.utcnow().isoformat()
                        }}
                    )
                    
    return {
        "message": "File uploaded successfully",
        "filename": sanitized_filename,
        "original_filename": file.filename,
        "file_url": file_url
    }

