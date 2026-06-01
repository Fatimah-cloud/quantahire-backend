import os
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from raganything import RAGAnything, RAGAnythingConfig
from config import TOP_K_FOR_LLM, RAG_STORAGE, WEIGHT_SIM, WEIGHT_LLM, MAX_ROUNDS
from services.llm import llm_func, vision_func
from services.embeddings import hf_embedding_func, embedding_func

# ── RAG / Knowledge Graph setup ──────────────────────────────────────────────
rag_config = RAGAnythingConfig(
    working_dir              = RAG_STORAGE,
    parser                   = "mineru",
    parse_method             = "auto",
    enable_image_processing  = False,
    enable_table_processing  = True,
    enable_equation_processing = False,
    display_content_stats    = False,
)

rag = RAGAnything(
    config            = rag_config,
    llm_model_func    = llm_func,
    vision_model_func = vision_func,
    embedding_func    = embedding_func,
)

# ── Scoring ───────────────────────────────────────────────────────────────────
SCORE_SYSTEM = (
    "You are a professional HR that rates resumes. Generate a score on the scale 1–5 for each "
    "work experience match, skills match, educational background match and certifications/extracurricular "
    "match based on the job description summary and resume. Additionally provide the reasons for the "
    "generated rating. Be strict in rating.\n\n"
    "The format of the output should be exactly like following:\n\n"
    "Rating: \n"
    "Work Experience Match: \n"
    "Skills Match: \n"
    "Educational Background Match\n"
    "Certifications/Extracurricular Match: \n\n"
    "Reasons for rating:\n"
)

REWRITE_SYSTEM = (
    "You are an expert HR recruiter. The search query did not find "
    "the right candidates according to the recruiter's feedback.\n"
    "The recruiter rates candidates on: work experience, skills, education, and certifications.\n"
    "Rewrite the query to better match what the recruiter wants, focusing on these four areas.\n"
    "Output ONLY the new search query, nothing else."
)

def parse_rating(resp: str):
    import re
    scores  = {"work_exp": 3, "skills": 3, "education": 3, "certifications": 3}
    reasons = {"work_exp": "", "skills": "", "education": "", "certifications": ""}
    lines   = resp.strip().split("\n")
    in_rating, in_reasons = True, False
    reason_accum = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "Rating:" in line:
            continue
        if "Reasons for rating:" in line:
            in_rating, in_reasons = False, True
            continue
        if in_rating:
            cleaned = line.replace("*", "").replace("-", "").strip()
            cleaned = re.sub(r'^\d+[\.\)\s]+', '', cleaned).strip()
            
            for key, prefix in [
                ("work_exp",      "Work Experience Match"),
                ("skills",        "Skills Match"),
                ("education",     "Educational Background Match"),
                ("certifications","Certifications/Extracurricular Match"),
            ]:
                if prefix.lower() in cleaned.lower():
                    try:
                        digits = re.findall(r'\b[1-5]\b', cleaned)
                        if digits:
                            scores[key] = int(digits[0])
                    except:
                        pass
        elif in_reasons:
            reason_accum.append(line)

    full  = " ".join(reason_accum)
    parts = [p.strip() + "." for p in full.split(".") if p.strip()]
    for i, key in enumerate(["work_exp", "skills", "education", "certifications"]):
        reasons[key] = parts[i] if i < len(parts) else (full[:100] if i == 0 else "")
    reasons["explanation"] = full
    return scores, reasons

def total_match_from_scores(scores: dict) -> float:
    avg   = sum(scores.values()) / 4.0
    total = (avg - 1) * 25
    return max(0, min(100, round(total, 1)))

def hybrid_score(similarity: float, llm_total: float) -> float:
    return round(WEIGHT_SIM * similarity + WEIGHT_LLM * llm_total, 1)

async def llm_score(jd_text: str, cv_context: str):
    prompt = (
        f"Job description summary:\n{jd_text[:3000]}\n\n"
        f"Resume content:\n{(cv_context or '')[:5000]}"
    )
    try:
        resp             = await llm_func(prompt=prompt, system_prompt=SCORE_SYSTEM)
        print(f"[DEBUG matcher.py llm_score] Extracted CV text length: {len(cv_context or '')}")
        print(f"[DEBUG matcher.py llm_score] Raw LLM Response:\n{resp}")
        scores, reasons  = parse_rating(resp)
        print(f"[DEBUG matcher.py llm_score] Parsed Scores: {scores}")
        total            = total_match_from_scores(scores)
        verdict = (
            f"WE:{scores['work_exp']} Sk:{scores['skills']} "
            f"Ed:{scores['education']} Cert:{scores['certifications']} "
            f"| {reasons['skills'][:60]}"
        )
        return total, verdict, scores, reasons
    except Exception as e:
        print(f"[DEBUG matcher.py llm_score] Exception encountered: {e}")
        return 50, f"LLM error: {str(e)[:100]}", {}, {}

def build_query(cv_id: str, category: str, jd_text: str) -> str:
    return (
        f"Skills and experience of '{cv_id}' in {category}. "
        f"Relevant to: {jd_text[:2000]}"
    )

async def rewrite_query(jd_text: str, current_query: str, feedback: str, history=None) -> str:
    history_text = ""
    if history:
        history_text = "\nPREVIOUS ATTEMPTS:\n"
        for h in history:
            history_text += (
                f"  Round {h['round']}: Top was {h['top_cv']} "
                f"(score {h['top_score']})\n"
            )
            if h.get("feedback"):
                history_text += f"    Recruiter: {h['feedback']}\n"

    prompt = (
        f"JOB DESCRIPTION:\n{jd_text[:400]}\n\n"
        f"CURRENT QUERY:\n{current_query}\n\n"
        f"RECRUITER FEEDBACK:\n{feedback}\n"
        f"{history_text}\n"
        "Write an improved search query. Output ONLY the query."
    )
    try:
        result = await llm_func(prompt=prompt, system_prompt=REWRITE_SYSTEM)
        return result.strip() if result else current_query
    except:
        return current_query

# ── Main ranking function ─────────────────────────────────────────────────────
async def rank_cvs(jd_text: str, cv_records: list, query_override: dict = None) -> list:
    """
    cv_records: list of dicts with keys: cv_id, text, category
    Returns: list of result dicts sorted by final_score descending
    """
    jd_emb     = await hf_embedding_func([jd_text])
    sim_scores = []

    for cv in cv_records:
        text = cv.get("text", "")
        if not text:
            sim_scores.append((cv, 0.0))
            continue
        cv_emb = await hf_embedding_func([text])
        sim    = cosine_similarity(jd_emb, cv_emb)[0][0]
        sim_scores.append((cv, round(max(0.0, float(sim)) * 100, 1)))

    sim_scores.sort(key=lambda x: x[1], reverse=True)
    top_k = sim_scores[:TOP_K_FOR_LLM]
    rest  = sim_scores[TOP_K_FOR_LLM:]

    print(f"[DEBUG matcher.py rank_cvs] Total CVs to rank: {len(cv_records)}")
    print(f"[DEBUG matcher.py rank_cvs] TOP_K_FOR_LLM value: {TOP_K_FOR_LLM}")
    print(f"[DEBUG matcher.py rank_cvs] Top K CVs for LLM scoring: {len(top_k)}")
    print(f"[DEBUG matcher.py rank_cvs] Rest (similarity only): {len(rest)}")

    rows = []

    # Stage B: LLM deep scoring for top-K
    for cv, sim_score in top_k:
        query   = (query_override or {}).get(cv["cv_id"], build_query(cv["cv_id"], cv.get("category", "General"), jd_text))
        cv_text = cv.get("text", "")

        try:
            rag_ctx = await rag.aquery(query=query, mode="hybrid", top_k=10)
            context = cv_text + ("\n\n" + rag_ctx if rag_ctx and len(rag_ctx.strip()) > 100 else "")
        except:
            context = cv_text

        llm_total, verdict, scores, reasons = await llm_score(jd_text, context)
        final = hybrid_score(sim_score, llm_total)

        rows.append({
            "cv_id":       cv["cv_id"],
            "filename":    cv.get("original_filename", cv["cv_id"]),
            "category":    cv.get("category", "General"),
            "similarity":  sim_score,
            "llm_total":   llm_total,
            "final_score": final,
            "verdict":     verdict,
            "scores":      scores,
            "reasons":     reasons,
        })

    # Stage C: rest — similarity only
    for cv, sim_score in rest:
        rows.append({
            "cv_id":       cv["cv_id"],
            "filename":    cv.get("original_filename", cv["cv_id"]),
            "category":    cv.get("category", "General"),
            "similarity":  sim_score,
            "llm_total":   None,
            "final_score": sim_score,
            "verdict":     f"[Similarity only — ranked below top {TOP_K_FOR_LLM}]",
            "scores":      {},
            "reasons":     {},
        })

    rows.sort(key=lambda x: x["final_score"], reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1

    return rows


async def generate_candidate_feedback(match_score: float, job_title: str, job_description: str, cv_summary: str = None) -> str:
    """
    Generate professional and constructive candidate feedback using the LLM.
    """
    prompt = (
        f"You are a professional HR recruiter/assistant.\n"
        f"Please generate a personalized feedback message for a candidate who applied to the '{job_title}' role.\n"
        f"The candidate has a compatibility match score of {match_score}%.\n"
    )
    if job_description:
        prompt += f"Job Description:\n{job_description[:1000]}\n\n"
    if cv_summary:
        prompt += f"Candidate CV/Resume summary/details:\n{cv_summary[:1500]}\n\n"
        
    prompt += (
        "Generate a professional, encouraging, and specific feedback message (about 2-4 sentences) "
        "discussing their qualifications, strengths, and areas they match or could improve on based on the match score. "
        "Address the candidate directly as 'you'. "
        "Do not include any system/prompt instructions, headers, or recruiter placeholders/signatures (e.g., '[Your Name]'). "
        "Write only the feedback text itself."
    )
    
    system_prompt = (
        "You are an expert HR recruiter assistant. You write helpful, constructive, and professional "
        "feedback messages directly addressed to candidates, based on their match scores and job requirements."
    )
    
    try:
        feedback = await llm_func(prompt=prompt, system_prompt=system_prompt)
        if feedback and feedback.strip():
            return feedback.strip()
    except Exception as e:
        print(f"Error generating AI feedback: {e}")
        
    # Return a fallback template if LLM fails or returns empty response
    if match_score >= 80:
        return f"Thank you for applying to the {job_title} position. Your impressive profile has a compatibility match score of {match_score}%, showing a strong alignment with our requirements. We will contact you soon."
    elif match_score >= 50:
        return f"Thank you for your interest in the {job_title} role. Your qualifications match several key requirements, resulting in a compatibility score of {match_score}%. We will keep you updated as we review all applications."
    else:
        return f"Thank you for your application for the {job_title} role. We appreciate your interest, but with a compatibility score of {match_score}%, we have decided to focus on other applicants whose skills closer fit our immediate needs."

