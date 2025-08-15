# scripts/train_fit_model.py
"""
Train a tiny RoleFit v2 classifier using synthetic pairs.
Feature: cosine similarity between JD and resume.
Label: 1 if JD looks like a good ML/DS match; else 0.
Saves models/fit_clf.joblib
"""

from pathlib import Path
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
import yaml

# --- Resolve project root and data paths robustly ---
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"

PROFILE_PATH = DATA_DIR / "profile.yaml"
RESUME_PATH = DATA_DIR / "base_resume.md"

# Lazy import so a clearer error appears if the lib is missing
try:
    from sentence_transformers import SentenceTransformer
except Exception as e:
    raise SystemExit(
        "sentence-transformers is required for training.\n"
        "Install with:  pip install sentence-transformers\n"
        f"Original error: {e}"
    )

# --- Load profile (optional, not strictly needed for this toy trainer) ---
PROFILE = {}
if PROFILE_PATH.exists():
    PROFILE = yaml.safe_load(PROFILE_PATH.read_text()) or {}

def mk_jd(pos: bool = True) -> str:
    """Create quick synthetic JDs (positive vs negative)."""
    core = "We are hiring for a Machine Learning / Data role. "
    base = "Looking for experience in Python, SQL, Spark, AWS. "
    extras = "Bonus: Airflow, Databricks, Docker, Kubernetes. "
    noise = "We value teamwork, growth mindset, and clear communication. "
    if pos:
        return core + base + extras + noise
    return core + "Preferred: Java, PHP, Photoshop, sales experience. " + noise

def make_dataset(n: int = 300):
    """Build (X, y) with a single feature: JD/Resume cosine similarity."""
    if not RESUME_PATH.exists():
        raise FileNotFoundError(f"Base resume not found at {RESUME_PATH}")
    resume = RESUME_PATH.read_text()

    enc = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    X, y = [], []
    for i in range(n):
        pos = (i % 2 == 0)
        jd = mk_jd(pos=pos)
        e1 = enc.encode([jd], normalize_embeddings=True)
        e2 = enc.encode([resume], normalize_embeddings=True)
        cos = float(cosine_similarity(e1, e2)[0, 0])
        X.append([cos])
        y.append(1 if pos else 0)
    return np.array(X, dtype=float), np.array(y, dtype=int)

def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    X, y = make_dataset(300)
    clf = LogisticRegression()
    clf.fit(X, y)
    out_path = MODELS_DIR / "fit_clf.joblib"
    joblib.dump(clf, out_path)
    print(f"Saved {out_path}")
    print("Example probs:", clf.predict_proba(X[:5])[:, 1])

if __name__ == "__main__":
    main()
