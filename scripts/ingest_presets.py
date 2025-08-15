# scripts/ingest_presets.py
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path

def read_slugs(file_path: str) -> list[str]:
    p = Path(file_path)
    if not p.exists():
        print(f"[ingest_presets] Slug file not found: {p}")
        return []
    slugs = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        slugs.append(line)
    return slugs

def run_one(slug: str, limit: int) -> int:
    cmd = [sys.executable, "-m", "scripts.ingest_greenhouse", "--board", slug, "--limit", str(limit)]
    print(f"[ingest_presets] → {slug}")
    try:
        return subprocess.run(cmd, check=False).returncode
    except Exception as e:
        print(f"[ingest_presets] ERROR {slug}: {e}")
        return 1

def main():
    ap = argparse.ArgumentParser(description="Ingest many Greenhouse boards from a preset list, using data/profile.yaml filters.")
    ap.add_argument("--file", default="data/greenhouse_slugs.txt", help="Path to newline-separated list of slugs.")
    ap.add_argument("--limit", type=int, default=50, help="Per-board job limit.")
    args = ap.parse_args()

    slugs = read_slugs(args.file)
    if not slugs:
        print("[ingest_presets] No slugs to ingest. Edit data/greenhouse_slugs.txt first.")
        sys.exit(0)

    total_rc = 0
    for slug in slugs:
        rc = run_one(slug, args.limit)
        total_rc |= rc

    print("[ingest_presets] Done.")
    sys.exit(total_rc)

if __name__ == "__main__":
    main()
