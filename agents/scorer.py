# agents/scorer.py
from sentence_transformers import SentenceTransformer, util
import re

_model = SentenceTransformer("all-MiniLM-L6-v2")

def keyword_coverage(text, keywords):
    text_l = text.lower()
    hits = sum(1 for k in keywords if k.lower() in text_l)
    return hits / max(1, len(keywords))

def fit_score(jd_text, resume_text, required_keywords):
    emb = _model.encode([jd_text, resume_text], convert_to_tensor=True, normalize_embeddings=True)
    semantic = float(util.cos_sim(emb[0], emb[1])[0][0])
    keywords = keyword_coverage(resume_text, required_keywords)
    total = 0.7 * semantic + 0.3 * keywords
    return dict(total=total, semantic=semantic, keywords=keywords, rationale={
        "matched_keywords": [k for k in required_keywords if re.search(rf'\\b{k}\\b', resume_text, re.I)]
    })
