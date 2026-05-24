import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM ───────────────────────────────────────────────────────────────────────
# Swap to any OpenAI-compatible provider just by changing these in .env
LLM_API_KEY   = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL  = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL     = os.getenv("LLM_MODEL", "deepseek-chat")

# ── Embeddings ────────────────────────────────────────────────────────────────
# Any sentence-transformers model name works here
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "sentence-transformers/all-mpnet-base-v2")
EMBED_DIM        = int(os.getenv("EMBED_DIM", "768"))

# ── Ranking ───────────────────────────────────────────────────────────────────
TOP_K_FOR_LLM  = int(os.getenv("TOP_K_FOR_LLM", "10"))
WEIGHT_SIM     = float(os.getenv("WEIGHT_SIM", "0.3"))   # embedding similarity weight
WEIGHT_LLM     = float(os.getenv("WEIGHT_LLM", "0.7"))   # LLM score weight
MAX_ROUNDS     = int(os.getenv("MAX_ROUNDS", "3"))        # max human-in-the-loop rounds

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "quantahire")

# ── Storage ───────────────────────────────────────────────────────────────────
UPLOAD_DIR  = os.getenv("UPLOAD_DIR", "uploads")
RAG_STORAGE = os.getenv("RAG_STORAGE", "rag_storage")
