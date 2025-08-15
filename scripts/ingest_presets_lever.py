# scripts/ingest_presets_lever.py
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path

def read_list(p):
    path=Path(p)
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]

def main():
    ap=argparse.ArgumentParser(description="Ingest many Lever companies from data/lever_slugs.txt")
    ap.add_argument("--file", default="data/lever_slugs.txt")
    ap.add_argument("--limit", type=int, default=100)
    args=ap.parse_args()
    slugs=read_list(args.file)
    total=0
    for s in slugs:
        print(f"[ingest:lever] → {s}")
        rc=subprocess.run([sys.executable,"-m","scripts.ingest_lever","--company",s,"--limit",str(args.limit)],check=False)
        total |= rc.returncode
    print("[ingest:lever] Done."); sys.exit(total)

if __name__=="__main__":
    main()
