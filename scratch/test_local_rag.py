import asyncio
import os
os.environ["FLAGS_use_onednn"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
import sys

# Add project root to sys.path so we can import services correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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

async def test_local_rag():
    safe_print("🚀 Starting local RAG verification test...")
    
    # Step 1: Create a mock resume text file
    sample_path = "scratch/sample_resume.txt"
    os.makedirs("scratch", exist_ok=True)
    with open(sample_path, "w") as f:
        f.write(
            "Candidate: Layan Al-Duais\n"
            "Role: Senior Full Stack Engineer\n"
            "Experience:\n"
            " - Software Engineer at QuantaHire (2024 - Present): Built an agentic recruitment pipeline using LightRAG, FastAPI, and MongoDB.\n"
            " - Frontend Developer at Quanta (2022 - 2024): Built responsive dashboards using React and TailwindCSS.\n"
            "Skills: Python, JavaScript, React, RAG, MongoDB, AWS, Docker.\n"
        )
    safe_print(f"📝 Created sample resume: {sample_path}")
    
    # Step 2: Index the file through RAG
    try:
        safe_print("🔍 Indexing sample resume into RAGAnything knowledge graph...")
        await rag.process_document_complete(sample_path)
        safe_print("✅ RAG indexing completed successfully!")
    except Exception as e:
        safe_print(f"❌ RAG indexing failed: {e}")
        return
        
    # Step 3: Query the RAG database
    try:
        query = "What is Layan's experience with RAG and QuantaHire?"
        safe_print(f"\n💬 Querying RAG: '{query}'...")
        result = await rag.aquery(query=query, mode="hybrid")
        safe_print("\n📖 RAG Query Result:")
        safe_print("-" * 50)
        safe_print(result)
        safe_print("-" * 50)
    except Exception as e:
        safe_print(f"❌ RAG Query failed: {e}")
        
    # Step 4: Clean up - delete the temporary file
    if os.path.exists(sample_path):
        os.remove(sample_path)
        safe_print(f"\n🧹 Cleaned up temporary file: {sample_path}")

if __name__ == "__main__":
    asyncio.run(test_local_rag())
