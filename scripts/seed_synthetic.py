# scripts/seed_synthetic.py
from db.models import init_db, Session, JobPosting

init_db()
s = Session()
jobs = [
    dict(title="Machine Learning Engineer (Data focus)", company="Acme Health", location="Boston, MA",
         url="https://example.com/jobs/acme-mle", jd_text="""
We seek an MLE with strong data engineering foundations. Must have: Python, SQL, Spark, AWS.
Nice: Airflow, Snowflake, Databricks. Work with analysts to productionize models.
"""),
    dict(title="Data Scientist", company="Nova Retail", location="Seattle, WA",
         url="https://example.com/jobs/nova-ds", jd_text="""
Looking for a Data Scientist to build forecasting and uplift models.
Must have: Python, SQL. Nice: Spark, AWS, MLflow.
"""),
    dict(title="ML Ops Engineer", company="FinPeak", location="Remote - USA",
         url="https://example.com/jobs/finpeak-mlops", jd_text="""
Own ML pipelines (Docker, Kubernetes, CI/CD). Must have: Python, AWS.
Nice: Databricks, Airflow.
"""),
    dict(title="Software Engineer (Backend)", company="SkyLabs", location="San Jose, CA",
         url="https://example.com/jobs/skylabs-backend", jd_text="""
Build backend services in Python/FastAPI. Must have: Python, SQL, AWS.
Nice: Kubernetes, Airflow.
"""),
]
for j in jobs:
    if not s.query(JobPosting).filter_by(url=j["url"]).first():
        s.add(JobPosting(**j))
s.commit()
print("Seeded synthetic jobs.")
