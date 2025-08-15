from __future__ import annotations
import argparse, requests, re, sys
from pathlib import Path
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.models import Session, JobPosting
import yaml

REMOTE_TOKENS = ["remote", "remote - us", "remote (us)", "remote, us", "us (remote)", "usa (remote)", "united states (remote)"]
ROLE_SYNONYMS = ["machine learning","ml","ml engineer","mlops","ml ops","data scientist","software engineer","backend","data engineer"]

def _norm(s: str) -> str: return re.sub(r"\s+"," ",(s or "").lower()).strip()
def load_profile() -> dict:
    p=Path("data/profile.yaml"); return yaml.safe_load(p.read_text()) if p.exists() else {}

def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for br in soup.find_all("br"): br.replace_with("\n")
    for li in soup.find_all("li"): li.insert_before("• "); li.append("\n")
    for p in soup.find_all("p"): p.append("\n")
    text = soup.get_text()
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())

def allow_title(raw_title: str, profile: dict) -> bool:
    t=_norm(raw_title); wanted=[_norm(x) for x in (profile.get("target_roles") or [])]
    if not wanted: return True
    if any(all(piece in t for piece in role.split()) for role in wanted): return True
    tokens=set(ROLE_SYNONYMS)
    for w in wanted:
        for chunk in re.split(r"[^a-z]+", w):
            if len(chunk)>=3: tokens.add(chunk)
    return any(tok in t for tok in tokens)

def allow_location(raw_loc: str, profile: dict) -> bool:
    loc=_norm(raw_loc); wants=[_norm(x) for x in (profile.get("locations") or [])]
    if not wants: return True
    if any(tok in loc for tok in REMOTE_TOKENS):
        return any("remote" in w for w in wants)
    return any(w in loc for w in wants)

def allow_keywords(text_html: str, profile: dict) -> bool:
    text=_norm(_html_to_text(text_html))
    must=[_norm(k) for k in (profile.get("must_have_keywords") or [])]
    if not must: return True
    min_req=int((profile.get("filters") or {}).get("min_must_keywords", len(must)))
    return sum(1 for k in must if k in text) >= min_req

def _fetch(company: str, limit: int) -> List[Dict[str, Any]]:
    url=f"https://api.lever.co/v0/postings/{company}?mode=json"
    r=requests.get(url,timeout=30); r.raise_for_status()
    return (r.json() or [])[:limit]

def ingest(company: str, limit: int = 200) -> dict:
    profile=load_profile(); s=Session()
    stats={"company":company,"fetched":0,"kept":0,"deduped":0,"drop_role":0,"drop_loc":0,"drop_kw":0}
    rows=_fetch(company,limit); stats["fetched"]=len(rows)
    comp_name=company.replace("-"," ").title()

    for j in rows:
        title=j.get("text") or j.get("title") or ""
        location=(j.get("categories") or {}).get("location") or ""
        jd=j.get("descriptionPlain") or j.get("description") or j.get("content") or ""

        if not allow_title(title, profile): stats["drop_role"]+=1; continue
        if not allow_location(location, profile): stats["drop_loc"]+=1; continue
        if not allow_keywords(jd, profile): stats["drop_kw"]+=1; continue

        exists=(s.query(JobPosting)
                 .filter(JobPosting.company==comp_name)
                 .filter(JobPosting.title==title)
                 .filter(JobPosting.location==location)
                 .first())
        if exists: stats["deduped"]+=1; continue

        s.add(JobPosting(company=comp_name, title=title, location=location,
                         jd_text=_html_to_text(jd), posted_at=datetime.utcnow(), status="new"))
        stats["kept"]+=1
    s.commit(); return stats

def main():
    ap=argparse.ArgumentParser(description="Ingest jobs from Lever with profile.yaml filters.")
    ap.add_argument("--company", action="append", required=True, help="Lever slug (e.g., stripe, databricks). Can repeat.")
    ap.add_argument("--limit", type=int, default=200)
    args=ap.parse_args()
    total=0
    for c in args.company:
        try:
            st=ingest(c,limit=args.limit)
            print(f"[lever:{c}] fetched={st['fetched']} kept={st['kept']} drop(role={st['drop_role']}, loc={st['drop_loc']}, kw={st['drop_kw']}) deduped={st['deduped']}")
            total+=st["kept"]
        except requests.HTTPError as e:
            print(f"[lever:{c}] HTTP error: {e}")
        except Exception as e:
            print(f"[lever:{c}] failed: {e}")
    print(f"Done. Total added: {total}")

if __name__=="__main__":
    main()
