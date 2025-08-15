# main.py
import yaml
from pathlib import Path
from dotenv import load_dotenv
from db.models import init_db, Session, JobPosting, FitScore, Artifact
from agents.scorer import fit_score
from rag.store import SimpleStore
from agents.composer import compose_artifacts

load_dotenv()
init_db()

def load_base_resume() -> str:
    return Path("data/base_resume.md").read_text()

def required_keywords():
    prof = yaml.safe_load(Path("data/profile.yaml").read_text())
    return prof.get("must_have_keywords", [])

def main(top_n=2):
    s = Session()
    jobs = s.query(JobPosting).filter(JobPosting.status.in_(["ingested","scored"])).all()
    if not jobs:
        print("No jobs found. Run the seed script first.")
        return

    base_resume = load_base_resume()
    req_kws = required_keywords()

    # Score all jobs
    for job in jobs:
        sc = fit_score(job.jd_text, base_resume, req_kws)
        s.merge(FitScore(job_id=job.id,
                         total=sc["total"],
                         semantic=sc["semantic"],
                         keywords=sc["keywords"],
                         rationale=sc["rationale"]))
        job.status = "scored"
    s.commit()

    # Take top-N and generate artifacts
    top = s.query(FitScore).order_by(FitScore.total.desc()).limit(top_n).all()
    for fs in top:
        job = s.query(JobPosting).filter_by(id=fs.job_id).first()
        store = SimpleStore()
        store.add_texts([job.jd_text, f"{job.company} — {job.title}"])
        ctx = store.search(f"{job.company} {job.title}", k=3)

        out_dir = f"artifacts/{job.company}_{job.title}".replace(" ", "_")
        resume_p, cl_p, payload = compose_artifacts(job, base_resume, ctx, out_dir)
        s.add(Artifact(job_id=job.id,
                       resume_path=resume_p,
                       cover_letter_path=cl_p,
                       qa_json=payload))
        print(f"Generated: {resume_p} and {cl_p}")
    s.commit()

if __name__ == "__main__":
    main()
