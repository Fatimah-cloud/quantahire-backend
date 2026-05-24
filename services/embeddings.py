import numpy as np
from sentence_transformers import SentenceTransformer
from lightrag.utils import EmbeddingFunc
from config import EMBED_MODEL_NAME, EMBED_DIM

print(f"Loading embedding model: {EMBED_MODEL_NAME}...")
_embed_model = SentenceTransformer(EMBED_MODEL_NAME)
print("✅ Embedding model loaded.")

async def hf_embedding_func(texts: list) -> np.ndarray:
    return _embed_model.encode(texts, normalize_embeddings=True)

embedding_func = EmbeddingFunc(
    embedding_dim  = EMBED_DIM,
    max_token_size = 512,
    func           = hf_embedding_func,
)
