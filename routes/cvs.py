import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from db.mongo import cvs_col
from config import UPLOAD_DIR
import fitz
import docx as docx_lib

router = APIRouter(prefix="/api/cvs", tags=["CVs"])

def get_text(path: str) -> str:
    if path.endswith(".docx"):
        doc  = docx_lib.Document(path)
        text = " ".join(p.text for p in doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text += " " + cell.text
        return text
    elif path.endswith(".pdf"):
        doc  = fitz.open(path)
        text = " ".join(page.get_text() for page in doc)
        doc.close()
        return text
    return ""

@router.post("/upload")
async def upload_cvs(files: list[UploadFile] = File(...)):
    """
    Upload one or more CV files (.pdf, .docx) or a single .zip containing them.
    Extracted text is saved to MongoDB.
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    saved = []

    for upload in files:
        content  = await upload.read()
        filename = upload.filename.lower()

        if filename.endswith(".zip"):
            # Extract zip and process each CV inside
            with tempfile.TemporaryDirectory() as tmp:
                zip_path = os.path.join(tmp, "upload.zip")
                with open(zip_path, "wb") as f:
                    f.write(content)
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(tmp)
                for fp in Path(tmp).rglob("*"):
                    if fp.is_file() and fp.suffix.lower() in {".docx", ".pdf"}:
                        dest = os.path.join(UPLOAD_DIR, fp.name)
                        shutil.copy2(fp, dest)
                        text    = get_text(dest)
                        cv_id   = fp.stem
                        cv_data = {
                            "cv_id":             cv_id,
                            "original_filename": fp.name,
                            "category":          "General",
                            "text":              text,
                            "path":              dest,
                        }
                        await cvs_col.update_one(
                            {"cv_id": cv_id},
                            {"$set": cv_data},
                            upsert=True,
                        )
                        saved.append(cv_id)
        elif filename.endswith((".pdf", ".docx")):
            dest  = os.path.join(UPLOAD_DIR, upload.filename)
            with open(dest, "wb") as f:
                f.write(content)
            text    = get_text(dest)
            cv_id   = Path(upload.filename).stem
            cv_data = {
                "cv_id":             cv_id,
                "original_filename": upload.filename,
                "category":          "General",
                "text":              text,
                "path":              dest,
            }
            await cvs_col.update_one(
                {"cv_id": cv_id},
                {"$set": cv_data},
                upsert=True,
            )
            saved.append(cv_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {upload.filename}")

    return {"message": f"Uploaded {len(saved)} CV(s)", "cv_ids": saved}


@router.get("/")
async def list_cvs():
    """Return all CVs stored in MongoDB."""
    cvs = await cvs_col.find({}, {"_id": 0, "text": 0}).to_list(length=1000)
    return {"count": len(cvs), "cvs": cvs}


@router.delete("/{cv_id}")
async def delete_cv(cv_id: str):
    result = await cvs_col.delete_one({"cv_id": cv_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="CV not found")
    return {"message": f"Deleted CV: {cv_id}"}
