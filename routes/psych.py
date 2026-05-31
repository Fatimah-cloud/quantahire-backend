import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from db.mongo import db
from bson import ObjectId
from routes.auth import get_user_by_token
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/api/psych", tags=["Psychometric"])

# Seed data for questions
QUESTIONS_SEED = [
    { "order_index": 1, "trait": "openness", "text": "I enjoy exploring new ideas and creative approaches.", "is_reverse_scored": False },
    { "order_index": 2, "trait": "openness", "text": "I am uncomfortable when plans change unexpectedly.", "is_reverse_scored": True },
    { "order_index": 3, "trait": "conscientiousness", "text": "I consistently meet deadlines and follow through on commitments.", "is_reverse_scored": False },
    { "order_index": 4, "trait": "conscientiousness", "text": "I tend to act on impulse rather than planning ahead.", "is_reverse_scored": True },
    { "order_index": 5, "trait": "extraversion", "text": "I feel energized after working closely with a team.", "is_reverse_scored": False },
    { "order_index": 6, "trait": "extraversion", "text": "I find prolonged social interaction draining.", "is_reverse_scored": True },
    { "order_index": 7, "trait": "agreeableness", "text": "I am willing to compromise to reach a solution that works for everyone.", "is_reverse_scored": False },
    { "order_index": 8, "trait": "agreeableness", "text": "I find it difficult to trust coworkers with important tasks.", "is_reverse_scored": True },
    { "order_index": 9, "trait": "neuroticism", "text": "I stay calm and focused under pressure or tight deadlines.", "is_reverse_scored": False },
    { "order_index": 10, "trait": "neuroticism", "text": "Small frustrations at work tend to affect my mood significantly.", "is_reverse_scored": True }
]

class AnswerItem(BaseModel):
    question_id: str
    score: int

class SubmitRequest(BaseModel):
    answers: List[AnswerItem]

def match_jobs(scores: dict):
    # high is >= 3.5, low is < 3.5
    stability_score = scores.get("neuroticism", 0.0)
    
    rules = [
        {"high": ["openness", "conscientiousness"], "jobs": ["UX Designer", "Product Manager", "Architect", "Research Scientist"], "reason": "Your creativity combined with strong discipline makes you ideal for roles that need both innovation and precision."},
        {"high": ["openness", "extraversion"], "jobs": ["Marketing Manager", "Public Relations", "Brand Strategist", "Creative Director"], "reason": "Your curiosity and social energy suit roles where you communicate big ideas to wide audiences."},
        {"high": ["openness"], "low": ["extraversion"], "jobs": ["Writer", "Researcher", "Data Scientist", "Graphic Designer", "Animator"], "reason": "Your creative thinking paired with independent focus fits roles that require deep solo work on original ideas."},
        {"high": ["conscientiousness", "extraversion"], "jobs": ["Project Manager", "Operations Manager", "Team Lead", "Account Manager"], "reason": "Your reliability and people skills make you a natural leader who keeps teams organized and motivated."},
        {"high": ["conscientiousness"], "low": ["extraversion"], "jobs": ["Accountant", "Software Engineer", "Quality Assurance", "Data Analyst", "Compliance Officer"], "reason": "Your attention to detail and preference for focused work suit roles requiring precision and deep concentration."},
        {"high": ["extraversion", "agreeableness"], "jobs": ["Sales Representative", "HR Manager", "Customer Success", "Recruiter", "Teacher"], "reason": "Your warmth and social confidence make you excellent at building relationships and helping others."},
        {"high": ["extraversion"], "low": ["agreeableness"], "jobs": ["Lawyer", "Executive", "Entrepreneur", "Business Development", "Negotiator"], "reason": "Your assertiveness and social confidence suit competitive environments where tough decisions are routine."},
        {"high": ["agreeableness", "stability"], "jobs": ["Nurse", "Social Worker", "Counselor", "Therapist", "Customer Support Lead"], "reason": "Your calm empathy and emotional resilience make you outstanding in caregiving and support roles."},
        {"high": ["agreeableness"], "low": ["extraversion"], "jobs": ["Technical Writer", "Librarian", "Veterinarian", "Backend Developer"], "reason": "Your helpfulness and quiet focus suit roles where you support others through careful, behind-the-scenes work."},
        {"high": ["stability", "conscientiousness"], "jobs": ["Surgeon", "Air Traffic Controller", "Financial Analyst", "DevOps Engineer", "Pharmacist"], "reason": "Your composure under pressure and strong discipline make you perfect for high-stakes precision roles."},
        {"high": ["stability", "openness"], "jobs": ["Startup Founder", "Consultant", "Journalist", "Documentary Filmmaker"], "reason": "Your resilience and curiosity equip you for roles that require navigating uncertainty while exploring new territory."},
        {"high": ["conscientiousness"], "low": ["openness"], "jobs": ["Auditor", "Bank Teller", "Administrative Assistant", "Logistics Coordinator"], "reason": "Your reliability and preference for structure make you excellent in process-driven roles with clear expectations."},
        {"high": ["stability"], "low": ["openness"], "jobs": ["Security Analyst", "Database Administrator", "Manufacturing Supervisor"], "reason": "Your composure and preference for stability suit roles maintaining critical systems and consistent operations."},
        {"high": ["openness", "agreeableness"], "jobs": ["Teacher", "Counselor", "UX Researcher", "Nonprofit Manager", "Mediator"], "reason": "Your empathy and open-mindedness make you effective in roles that require understanding diverse perspectives."},
        {"high": ["conscientiousness", "agreeableness"], "jobs": ["Nurse", "Project Coordinator", "Office Manager", "Event Planner"], "reason": "Your organizational skills and team-oriented nature make you great at coordinating people and processes."},
    ]
    
    for rule in rules:
        high_reqs = rule.get("high", [])
        low_reqs = rule.get("low", [])
        
        match = True
        for trait in high_reqs:
            val = stability_score if trait == "stability" else scores.get(trait, 0.0)
            if val < 3.5:
                match = False
                break
        if not match:
            continue
            
        for trait in low_reqs:
            val = stability_score if trait == "stability" else scores.get(trait, 0.0)
            if val >= 3.5:
                match = False
                break
        if not match:
            continue
            
        return rule["jobs"], rule["reason"]
        
    return ["Accountant", "Software Engineer", "Quality Assurance", "Data Analyst", "Compliance Officer"], "Your balanced profile suits a wide variety of professional environments."

async def run_seed():
    psych_col = db["psych_questions"]
    await psych_col.delete_many({})
    docs = []
    for q in QUESTIONS_SEED:
        docs.append({
            "id": f"q_{q['order_index']}",
            "order_index": q["order_index"],
            "trait": q["trait"],
            "text": q["text"],
            "is_reverse_scored": q["is_reverse_scored"]
        })
    await psych_col.insert_many(docs)
    # Create indexes for assessment_results
    await db["assessment_results"].create_index("candidate_email")
    await db["assessment_results"].create_index([("created_date", -1)])

@router.get("/questions")
async def get_questions():
    questions = await db["psych_questions"].find().to_list(length=100)
    questions.sort(key=lambda x: x.get("order_index", 0))
    for q in questions:
        q["_id"] = str(q["_id"])
    return questions

@router.post("/submit")
async def submit_answers(req: SubmitRequest, user: dict = Depends(get_user_by_token)):
    if user.get("role") != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can submit test results")
        
    questions = await db["psych_questions"].find().to_list(length=100)
    q_map = {q["id"]: q for q in questions}
    
    sums = {"openness": 0, "conscientiousness": 0, "extraversion": 0, "agreeableness": 0, "neuroticism": 0}
    counts = {"openness": 0, "conscientiousness": 0, "extraversion": 0, "agreeableness": 0, "neuroticism": 0}
    
    for ans in req.answers:
        q = q_map.get(ans.question_id)
        if not q:
            continue
        trait = q["trait"]
        score = ans.score
        if q.get("is_reverse_scored"):
            score = 6 - score
        sums[trait] += score
        counts[trait] += 1
        
    scores = {}
    for trait in sums:
        scores[trait] = round(sums[trait] / counts[trait], 2) if counts[trait] > 0 else 0.0
        
    recommended_jobs, recommended_reason = match_jobs(scores)
    
    user_doc = await db["users"].find_one({"id": user["id"]})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User profile not found")
        
    candidate_id = user_doc["_id"]
    
    result_id = f"asmt_{uuid.uuid4().hex[:8]}"
    result_doc = {
        "id": result_id,
        "candidate_id": candidate_id,
        "candidate_name": user.get("full_name", "") or user_doc.get("full_name", ""),
        "candidate_email": user["email"],
        "score_openness": scores["openness"],
        "score_conscientiousness": scores["conscientiousness"],
        "score_extraversion": scores["extraversion"],
        "score_agreeableness": scores["agreeableness"],
        "score_neuroticism": scores["neuroticism"],
        "recommended_jobs": recommended_jobs,
        "recommended_reason": recommended_reason,
        "created_date": datetime.utcnow().isoformat(),
        "answers": {ans.question_id: ans.score for ans in req.answers}
    }
    
    await db["assessment_results"].insert_one(result_doc)
    
    return {
        "success": True,
        "id": result_id,
        "scores": scores,
        "recommended_jobs": recommended_jobs,
        "recommended_reason": recommended_reason
    }

@router.get("/results")
async def get_results(user: dict = Depends(get_user_by_token)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admin accounts can access all results")
        
    results = await db["assessment_results"].find().to_list(length=1000)
    for r in results:
        r["_id"] = str(r["_id"])
        # Ensure candidate_id is stringified for JSON serialization
        if "candidate_id" in r:
            r["candidate_id"] = str(r["candidate_id"])
    return results

@router.post("/seed")
async def seed_questions():
    try:
        await run_seed()
        return {"success": True, "message": "Successfully seeded psychometric questions and created indexes"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
