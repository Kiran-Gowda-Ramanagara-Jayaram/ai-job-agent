# scripts/ingest_presets_ashby.py
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path

def read_list(p):
    path=Path(p)
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]

def main():
    ap=argparse.ArgumentParser(description="Ingest many Ashby orgs from data/ashby_orgs.txt")
    ap.add_argument("--file", default="data/ashby_orgs.txt")
    ap.add_argument("--limit", type=int, default=100)
    args=ap.parse_args()
    orgs=read_list(args.file)
    total=0
    for o in orgs:
        print(f"[ingest:ashby] → {o}")
        rc=subprocess.run([sys.executable,"-m","scripts.ingest_ashby","--org",o,"--limit",str(args.limit)],check=False)
        total |= rc.returncode
    print("[ingest:ashby] Done."); sys.exit(total)

if __name__=="__main__":
    main()
