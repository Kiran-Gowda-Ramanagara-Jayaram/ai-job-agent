# agents/rolefit.py
import os
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
import joblib

_EMB_MODEL = None
_CLF_PATH = Path("models/fit_clf.joblib")

def _embedder():
    global _EMB_MODEL
    if _EMB_MODEL is None:
        _EMB_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _EMB_MODEL

def _cos_sim(a: str, b: str) -> float:
    enc = _embedder()
    ea = enc.encode([a], normalize_embeddings=True)
    eb = enc.encode([b], normalize_embeddings=True)
    return float(cosine_similarity(ea, eb)[0,0])

def rolefit_score(jd_text: str, resume_md: str) -> float | None:
    """
    Returns probability (0..1) from the trained logistic regression on simple features:
    [cosine_similarity(jd, resume)]  — if model exists. Else None.
    """
    if not _CLF_PATH.exists():
        return None
    clf: LogisticRegression = joblib.load(_CLF_PATH)
    x = np.array([[ _cos_sim(jd_text, resume_md) ]], dtype=float)
    p = float(clf.predict_proba(x)[0,1])
    return p
