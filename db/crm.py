# db/crm.py
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os

DB_URL = os.getenv("DB_URL", "sqlite:///db/jobs.db")
engine = create_engine(DB_URL, echo=False)
Session = sessionmaker(bind=engine)
Base = declarative_base()

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    title = Column(String)
    company = Column(String)
    email = Column(String)
    linkedin_url = Column(String)
    source = Column(String)              # portal|linkedin|manual|hunter_*
    created_at = Column(DateTime, default=datetime.utcnow)

class OutreachEvent(Base):
    __tablename__ = "outreach_events"
    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"))
    job_id = Column(String)              # references job_postings.id
    channel = Column(String)             # email|linkedin|portal
    template_name = Column(String)
    sent_at = Column(DateTime, default=datetime.utcnow)
    outcome = Column(String)             # no_reply|reply|bounce|screen_invite
    notes = Column(Text)
    contact = relationship("Contact")

def init_crm():
    Base.metadata.create_all(engine)
