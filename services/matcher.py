# services/matcher.py  —  Full RAG pipeline with per-job knowledge graph.

import os
os.environ["FLAGS_use_onednn"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from raganything import RAGAnything, RAGAnythingConfig
from lightrag.utils import EmbeddingFunc
from config import TOP_K_FOR_LLM, RAG_STORAGE, WEIGHT_SIM, WEIGHT_LLM, MAX_ROUNDS
from services.llm import llm_func, vision_func
from services.embeddings import hf_embedding_func, embedding_func

# One RAGAnything instance per job_id, keyed by job_id string
_rag_instances: dict[str, RAGAnything] = {}


def get_rag_for_job(job_id: str) -> RAGAnything:
    """Return a cached (or newly created) RAGAnything instance for this job."""
    if job_id in _rag_instances:
        return _rag_instances[job_id]

    job_storage = os.path.join(RAG_STORAGE, job_id)
    os.makedirs(job_storage, exist_ok=True)

    config = RAGAnythingConfig(
        working_dir=job_storage,
        parser="mineru",
        parse_method="auto",
        enable_image_processing=False,
        enable_table_processing=True,
        enable_equation_processing=False,
        display_content_stats=False,
    )
    rag = RAGAnything(
        config=config,
        llm_model_func=llm_func,
        vision_model_func=vision_func,
        embedding_func=embedding_func,
    )
    _rag_instances[job_id] = rag
    return rag


async def index_cv_into_rag(cv_path: str, job_id: str) -> bool:
    """
    Parse and index a CV file into the knowledge graph for a specific job.
    Called once at upload time. Returns True on success.
    """
    if not os.path.exists(cv_path):
        print(f"[RAG index] File not found: {cv_path}")
        return False

    rag = get_rag_for_job(job_id)
    try:
        await rag.process_document_complete(
            file_path=cv_path,
            output_dir=os.path.join(RAG_STORAGE, job_id, "parsed"),
        )
        print(f"[RAG index] Indexed {os.path.basename(cv_path)} into job graph '{job_id}'")
        return True
    except Exception as e:
        print(f"[RAG index] Failed to index {cv_path}: {e}")
        return False


SCORE_SYSTEM = (
    "You are a professional HR that rates resumes. Generate a score on the scale 1-5 for each "
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
                ("work_exp",       "Work Experience Match"),
                ("skills",         "Skills Match"),
                ("education",      "Educational Background Match"),
                ("certifications", "Certifications/Extracurricular Match"),
            ]:
                if prefix.lower() in cleaned.lower():
                    try:
                        digits = re.findall(r'\b[1-5]\b', cleaned)
                        if digits:
                            scores[key] = int(digits[0])
                    except Exception:
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
        resp            = await llm_func(prompt=prompt, system_prompt=SCORE_SYSTEM)
        scores, reasons = parse_rating(resp)
        total           = total_match_from_scores(scores)
        verdict = (
            f"WE:{scores['work_exp']} Sk:{scores['skills']} "
            f"Ed:{scores['education']} Cert:{scores['certifications']} "
            f"| {reasons['skills'][:60]}"
        )
        return total, verdict, scores, reasons
    except Exception as e:
        print(f"[LLM score] error: {e}")
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
    except Exception:
        return current_query


async def rank_cvs(jd_text: str, cv_records: list, job_id: str, query_override: dict = None) -> list:
    """
    Two-stage ranking for a specific job's candidates.
    cv_records: list of dicts with keys: cv_id, text, category
    job_id: used to load the correct per-job RAG graph
    Returns: list of result dicts sorted by final_score descending
    """
    rag = get_rag_for_job(job_id)

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

    print(f"[rank_cvs] job={job_id} | total={len(cv_records)} | top_k={len(top_k)} | rest={len(rest)}")

    rows = []

    for cv, sim_score in top_k:
        query   = (query_override or {}).get(cv["cv_id"], build_query(cv["cv_id"], cv.get("category", "General"), jd_text))
        cv_text = cv.get("text", "")

        rag_ctx = ""
        try:
            rag_ctx = await rag.aquery(query=query, mode="hybrid", top_k=10)
            if rag_ctx and len(rag_ctx.strip()) > 100:
                print(f"[rank_cvs] RAG context retrieved for {cv['cv_id']} ({len(rag_ctx)} chars)")
            else:
                rag_ctx = ""
                print(f"[rank_cvs] RAG returned empty for {cv['cv_id']} — using raw CV text only")
        except Exception as e:
            print(f"[rank_cvs] RAG query error for {cv['cv_id']}: {e}")

        context = cv_text + ("\n\n" + rag_ctx if rag_ctx else "")
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
            "rag_used":    bool(rag_ctx),
        })

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
            "rag_used":    False,
        })

    rows.sort(key=lambda x: x["final_score"], reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return rows


async def generate_candidate_feedback(match_score: float, job_title: str, job_description: str, cv_summary: str = None) -> str:
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
        "Generate a professional, encouraging, and specific feedback message (about 2-4 sentences). "
        "Address the candidate directly as 'you'. "
        "Do not include headers or recruiter signatures. Write only the feedback text itself."
    )
    system_prompt = (
        "You are an expert HR recruiter assistant. You write helpful, constructive, and professional "
        "feedback messages directly addressed to candidates."
    )
    try:
        feedback = await llm_func(prompt=prompt, system_prompt=system_prompt)
        if feedback and feedback.strip():
            return feedback.strip()
    except Exception as e:
        print(f"[feedback gen] error: {e}")

    if match_score >= 80:
        return f"Thank you for applying to the {job_title} position. Your profile shows a strong alignment with our requirements at {match_score}% match. We will contact you soon."
    elif match_score >= 50:
        return f"Thank you for your interest in the {job_title} role. Your qualifications match several key requirements with a {match_score}% compatibility score. We will keep you updated."
    else:
        return f"Thank you for your application for the {job_title} role. We appreciate your interest, but we have decided to focus on other applicants whose skills more closely fit our immediate needs."
