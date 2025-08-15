# scripts/cleanup_jobs.py
from __future__ import annotations
import re, yaml
from pathlib import Path
from db.models import Session, JobPosting

REMOTE_TOKENS = [
    "remote", "remote - us", "remote - usa", "us (remote)", "usa (remote)",
    "united states (remote)", "us remote", "remote, us", "remote (us)"
]
def _norm(s: str) -> str:
    import re
    return re.sub(r"\s+", " ", (s or "").lower()).strip()

def load_profile():
    p = Path("data/profile.yaml")
    return yaml.safe_load(p.read_text()) if p.exists() else {}

def allow_title(raw_title: str, profile: dict) -> bool:
    t = _norm(raw_title)
    targets = [_norm(x) for x in (profile.get("target_roles") or [])]
    if not targets: return True
    return any(all(piece in t for piece in role.split()) for role in targets)

def allow_location(raw_loc: str, profile: dict) -> bool:
    loc = _norm(raw_loc)
    wants = [_norm(x) for x in (profile.get("locations") or [])]
    if not wants: return True
    is_remote = any(tok in loc for tok in REMOTE_TOKENS)
    if is_remote:
        wants_remote = any("remote" in w for w in wants)
        if not wants_remote: return False
        wants_us = any(("us" in w) or ("usa" in w) or ("united states" in w) for w in wants)
        if wants_us and not any(u in loc for u in ["us", "usa", "united states"]):
            return False
        return True
    return any(w in loc for w in wants)

def allow_keywords(text: str, profile: dict) -> bool:
    n = _norm(text)
    must = [_norm(k) for k in (profile.get("must_have_keywords") or [])]
    return all(k in n for k in must) if must else True

def main():
    prof = load_profile()
    s = Session()
    kept = removed = 0
    for j in s.query(JobPosting).all():
        if allow_title(j.title, prof) and allow_location(j.location or "", prof) and allow_keywords(j.jd_text or "", prof):
            kept += 1
        else:
            s.delete(j); removed += 1
    s.commit()
    print(f"kept {kept}, removed {removed}")

if __name__ == "__main__":
    main()
