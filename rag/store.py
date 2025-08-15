# rag/store.py
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

class SimpleStore:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.index = None
        self.texts = []

    def add_texts(self, texts):
        if not texts: return
        self.texts.extend(texts)
        X = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        if self.index is None:
            self.index = faiss.IndexFlatIP(X.shape[1])
        self.index.add(X)

    def search(self, query, k=5):
        if self.index is None: return []
        q = self.model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
        D, I = self.index.search(q, k)
        return [self.texts[i] for i in I[0] if i < len(self.texts)]
