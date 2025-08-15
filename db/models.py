# db/models.py
from sqlalchemy import create_engine, Column, String, Text, Float, DateTime, Integer, JSON, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import uuid, os

DB_URL = os.getenv("DB_URL", "sqlite:///db/jobs.db")  # SQLite file inside /db
engine = create_engine(DB_URL, echo=False)
Session = sessionmaker(bind=engine)
Base = declarative_base()

def gen_id():
    return str(uuid.uuid4())

class JobPosting(Base):
    __tablename__ = "job_postings"
    id = Column(String, primary_key=True, default=gen_id)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    url = Column(String, unique=True)
    jd_text = Column(Text)
    posted_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="ingested")  # ingested|scored|approved|applied
    __table_args__ = (UniqueConstraint('url', name='uq_url'),)

class FitScore(Base):
    __tablename__ = "fit_scores"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String)
    total = Column(Float)
    semantic = Column(Float)
    keywords = Column(Float)
    rationale = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class Artifact(Base):
    __tablename__ = "artifacts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String)
    resume_path = Column(String)
    cover_letter_path = Column(String)
    qa_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(engine)
