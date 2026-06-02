import asyncio
import os
import sys
import shutil

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import services.llm
import services.matcher
from services.matcher import rank_cvs, rewrite_query, get_rag_for_job
from db.mongo import db

# Mock LLM calls to isolate the test from the expired OpenAI key
async def mock_llm_func(prompt, system_prompt=None, **kwargs):
    if "REWRITE_SYSTEM" in str(system_prompt) or "expert hr recruiter" in str(system_prompt).lower():
        # Query rewrite mock
        if "cloud" in prompt.lower():
            return "cloud experience AWS GCP Azure DevOps Kubernetes"
        return "General Software Engineer"
        
    if "rates resumes" in str(system_prompt).lower():
        # Scoring mock: rate 5 if "cloud" or "aws" or "azure" in prompt, otherwise 3
        rating = 3
        if "cloud" in prompt.lower() or "aws" in prompt.lower() or "azure" in prompt.lower():
            rating = 5
            
        return f"""
Rating:
Work Experience Match: {rating}
Skills Match: {rating}
Educational Background Match: 4
Certifications/Extracurricular Match: 3

Reasons for rating:
The candidate work experience and skills match. Educational background aligns. Certifications are average.
"""
    return "General feedback"

services.llm.llm_func = mock_llm_func
services.matcher.llm_func = mock_llm_func

async def main():
    print("--- RUNNING INTEGRATION TEST FOR FEEDBACK RE-RANKING ---")
    
    # 1. Define job and sample candidates
    job_id = "test_job_123"
    jd_text = "Looking for a Software Engineer with some general python experience."
    
    # Clean up any existing RAG directory for this test job
    job_rag_dir = os.path.join("rag_storage", job_id)
    if os.path.exists(job_rag_dir):
        shutil.rmtree(job_rag_dir)
        print(f"Cleaned up previous RAG directory: {job_rag_dir}")
        
    # Create two test resumes on disk
    os.makedirs("uploads", exist_ok=True)
    
    cv1_path = os.path.join("uploads", "test_cv_python.txt")
    with open(cv1_path, "w", encoding="utf-8") as f:
        f.write("Candidate: Alice Pythonista\nExperience: Python Developer for 3 years. General backend development.")
        
    cv2_path = os.path.join("uploads", "test_cv_cloud.txt")
    with open(cv2_path, "w", encoding="utf-8") as f:
        f.write("Candidate: Bob Cloudmaster\nExperience: Cloud Engineer for 4 years. Heavy AWS, Kubernetes, Terraform, cloud native developer.")
        
    cv_records = [
        {
            "cv_id": "alice_id",
            "text": "Candidate: Alice Pythonista\nExperience: Python Developer for 3 years. General backend development.",
            "category": "General",
            "original_filename": "test_cv_python.txt",
            "path": cv1_path
        },
        {
            "cv_id": "bob_id",
            "text": "Candidate: Bob Cloudmaster\nExperience: Cloud Engineer for 4 years. Heavy AWS, Kubernetes, Terraform, cloud native developer.",
            "category": "General",
            "original_filename": "test_cv_cloud.txt",
            "path": cv2_path
        }
    ]
    
    # 2. Initial Ranking
    print("\n--- Running Round 1 (Initial Match) ---")
    results = await rank_cvs(jd_text, cv_records, job_id=job_id)
    
    print("\nRound 1 Results:")
    for r in results:
        print(f"  Candidate: {r['cv_id']} | Final Score: {r['final_score']} | RAG Used: {r['rag_used']}")
        
    # 3. Submit Feedback (Recruiter wants more cloud experience)
    feedback = "Need more cloud experience"
    print(f"\n--- Recruiter Feedback: '{feedback}' ---")
    
    # Simulate feedback round
    history = [
        {
            "round": 1,
            "top_cv": results[0]["cv_id"],
            "top_score": results[0]["final_score"],
            "feedback": feedback,
            "approved": False
        }
    ]
    
    # Rewrite the query
    base_q = f"Skills and experience of candidate relevant to: {jd_text}"
    new_q = await rewrite_query(jd_text, base_q, feedback, history)
    print(f"Rewritten Query: {new_q}")
    
    # Re-rank with overridden queries
    query_override = {cv["cv_id"]: new_q for cv in cv_records}
    new_results = await rank_cvs(jd_text, cv_records, job_id=job_id, query_override=query_override)
    
    print("\nRound 2 Results (After Feedback):")
    for r in new_results:
        print(f"  Candidate: {r['cv_id']} | Final Score: {r['final_score']} | RAG Used: {r['rag_used']}")
        
    # Clean up test files
    for path in [cv1_path, cv2_path]:
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(job_rag_dir):
        shutil.rmtree(job_rag_dir)
        
    print("\nTest completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
