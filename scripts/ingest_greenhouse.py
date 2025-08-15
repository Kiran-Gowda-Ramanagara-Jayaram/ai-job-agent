# scripts/ingest_greenhouse.py
from __future__ import annotations
import argparse, re, requests, sys
from pathlib import Path
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.models import Session, JobPosting

import yaml  # pip install pyyaml

REMOTE_TOKENS = [
    "remote", "remote - us", "remote - usa", "us (remote)", "usa (remote)",
    "united states (remote)", "us remote", "remote, us", "remote (us)"
]

ROLE_SYNONYMS = [
    "machine learning", "ml", "ml engineer", "mlops", "ml ops",
    "data scientist", "software engineer", "backend", "data engineer"
]

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()

def load_profile() -> dict:
    p = Path("data/profile.yaml")
    return yaml.safe_load(p.read_text()) if p.exists() else {}

def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for br in soup.find_all("br"): br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert_before("• "); li.append("\n")
    for p in soup.find_all("p"): p.append("\n")
    text = soup.get_text()
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())

def allow_title(raw_title: str, profile: dict) -> bool:
    t = _norm(raw_title)
    wanted = [_norm(x) for x in (profile.get("target_roles") or [])]
    loosen = bool((profile.get("filters") or {}).get("loosen_role_match", True))
    # if no targets provided, allow all
    if not wanted:
        return True
    # strict = all words in role appear in title (rare)
    strict_hit = any(all(piece in t for piece in role.split()) for role in wanted)
    if strict_hit:
        return True
    if not loosen:
        return False
    # loose: any synonym OR any target token chunk appears
    tokens = set(ROLE_SYNONYMS)
    for w in wanted:
        # break "Software Engineer (Backend)" into useful chunks
        for chunk in re.split(r"[^a-z]+", w):
            if len(chunk) >= 3:
                tokens.add(chunk)
    return any(tok in t for tok in tokens)

def allow_location(raw_loc: str, profile: dict) -> bool:
    loc = _norm(raw_loc)
    wants = [_norm(x) for x in (profile.get("locations") or [])]
    if not wants:
        return True
    is_remote = any(tok in loc for tok in REMOTE_TOKENS)
    if is_remote:
        # allow if user listed any remote-like preference
        if any("remote" in w for w in wants):
            # if user hinted US in their remote strings, prefer US-tagged remotes
            wants_us = any(("us" in w) or ("usa" in w) or ("united states" in w) for w in wants)
            if wants_us and not any(u in loc for u in ["us", "usa", "united states"]):
                # still allow generic "remote" if no country shown
                return True
            return True
        return False
    # non-remote: substring match
    return any(w in loc for w in wants)

def allow_keywords(jd_html: str, profile: dict) -> bool:
    text = _norm(_html_to_text(jd_html))
    must = [_norm(k) for k in (profile.get("must_have_keywords") or [])]
    if not must:
        return True
    min_req = int((profile.get("filters") or {}).get("min_must_keywords", len(must)))
    hits = sum(1 for k in must if k in text)
    return hits >= min_req

def _fetch_greenhouse_jobs(board: str, limit: int = 200) -> List[Dict[str, Any]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json() or {}
    return (data.get("jobs") or [])[:limit]

def ingest_board(board: str, limit: int = 200) -> dict:
    profile = load_profile()
    s = Session()
    stats = {"board": board, "fetched": 0, "kept": 0, "deduped": 0,
             "drop_role": 0, "drop_loc": 0, "drop_kw": 0}

    rows = _fetch_greenhouse_jobs(board, limit)
    stats["fetched"] = len(rows)

    for j in rows:
        title = j.get("title") or ""
        company = (j.get("departments") or [{}])[0].get("name") or board.capitalize()
        location_obj = j.get("offices") or j.get("location") or {}
        if isinstance(location_obj, dict):
            location = location_obj.get("name") or ""
        elif isinstance(location_obj, list) and location_obj:
            location = (location_obj[0] or {}).get("name") or ""
        else:
            location = ""
        jd_html = j.get("content") or ""

        if not allow_title(title, profile):   stats["drop_role"] += 1; continue
        if not allow_location(location, profile): stats["drop_loc"] += 1; continue
        if not allow_keywords(jd_html, profile):  stats["drop_kw"] += 1; continue

        exists = (s.query(JobPosting)
                    .filter(JobPosting.company == company)
                    .filter(JobPosting.title == title)
                    .filter(JobPosting.location == location)
                    .first())
        if exists:
            stats["deduped"] += 1; continue

        s.add(JobPosting(
            company=company,
            title=title,
            location=location,
            jd_text=_html_to_text(jd_html),
            posted_at=datetime.utcnow(),
            status="new",
        ))
        stats["kept"] += 1

    s.commit()
    return stats

def main():
    ap = argparse.ArgumentParser(description="Ingest jobs from Greenhouse with profile.yaml filters.")
    ap.add_argument("--board", action="append", required=True, help="Greenhouse slug (e.g., stripe, figma). Can repeat.")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    total = 0
    for b in args.board:
        try:
            st = ingest_board(b, limit=args.limit)
            print(f"[{b}] fetched={st['fetched']} kept={st['kept']} "
                  f"drop(role={st['drop_role']}, loc={st['drop_loc']}, kw={st['drop_kw']}) "
                  f"deduped={st['deduped']}")
            total += st["kept"]
        except requests.HTTPError as e:
            print(f"[{b}] HTTP error: {e}")
        except Exception as e:
            print(f"[{b}] failed: {e}")
    print(f"Done. Total added: {total}")

if __name__ == "__main__":
    main()
