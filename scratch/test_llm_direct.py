import asyncio
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.llm import llm_func
from services.matcher import SCORE_SYSTEM, parse_rating

async def main():
    jd_text = (
        "Role: Senior Full Stack Engineer\n"
        "Requirements:\n"
        " - 5+ years of experience with Python, JavaScript, and React.\n"
        " - Experience building RAG systems and working with FastAPI and MongoDB.\n"
        " - Bachelor's or Master's degree in Computer Science.\n"
    )
    cv_text = (
        "Candidate: Layan Al-Duais\n"
        "Role: Senior Full Stack Engineer\n"
        "Experience:\n"
        " - Software Engineer at QuantaHire (2024 - Present): Built an agentic recruitment pipeline using LightRAG, FastAPI, and MongoDB.\n"
        " - Frontend Developer at Quanta (2022 - 2024): Built responsive dashboards using React and TailwindCSS.\n"
        "Skills: Python, JavaScript, React, RAG, MongoDB, AWS, Docker.\n"
        "Education: BS in Computer Science (GPA 3.9/4.0)\n"
    )
    
    prompt = (
        f"Job description summary:\n{jd_text}\n\n"
        f"Resume content:\n{cv_text}"
    )
    
    print("Calling LLM...")
    resp = await llm_func(prompt=prompt, system_prompt=SCORE_SYSTEM)
    print("\n--- RAW LLM RESPONSE ---")
    print(resp)
    print("------------------------")
    
    scores, reasons = parse_rating(resp)
    print("\n--- PARSED SCORES ---")
    print(scores)
    print("---------------------")
    print("\n--- PARSED REASONS ---")
    print(reasons)
    print("-----------------------")

if __name__ == "__main__":
    asyncio.run(main())
