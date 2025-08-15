# app/dashboard.py
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
import numpy as np

# Use a non-interactive backend for Streamlit
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dotenv import load_dotenv
load_dotenv()

from db.models import Session as JobSession, JobPosting, FitScore
from db.crm import Session as CRMSession, Contact, OutreachEvent, init_crm

st.set_page_config(page_title="AI Job Agent — Dashboard", layout="wide")
st.title("AI Job Agent — Dashboard")

init_crm()

# ---------- helpers ----------
def df_jobs():
    s = JobSession()
    rows = s.query(JobPosting).all()
    return pd.DataFrame([{
        "job_id": j.id, "company": j.company, "title": j.title,
        "location": j.location, "status": j.status,
        "posted_at": j.posted_at
    } for j in rows])

def df_events():
    s = CRMSession()
    rows = s.query(OutreachEvent).all()
    return pd.DataFrame([{
        "event_id": r.id,
        "job_id": r.job_id,
        "contact_id": r.contact_id,
        "channel": r.channel,
        "template_name": r.template_name,
        "outcome": (r.outcome or "sent"),
        "notes": (r.notes or ""),
        "created_at": getattr(r, "created_at", None)
    } for r in rows])

def df_contacts():
    s = CRMSession()
    rows = s.query(Contact).all()
    return pd.DataFrame([{
        "contact_id": c.id,
        "name": c.name or "",
        "email": c.email or "",
        "title": c.title or "",
        "company": c.company or "",
        "linkedin_url": c.linkedin_url or "",
        "source": c.source or "",
        "created_at": getattr(c, "created_at", None),
    } for c in rows])

def is_success(outcome: str) -> bool:
    # tweak as needed
    return outcome in {"positive_reply", "interview", "offer"}

# ---------- load ----------
jobs = df_jobs()
events = df_events()
contacts = df_contacts()

# ---------- KPIs ----------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Jobs in queue", int(len(jobs)))
c2.metric("Applied", int((jobs.status == "applied").sum()) if not jobs.empty else 0)
c3.metric("Outreach events", int(len(events)))
c4.metric("Interviews logged", int((events.outcome == "interview").sum()) if not events.empty else 0)

st.markdown("---")

# ---------- Jobs by status ----------
st.subheader("Jobs by status")
if jobs.empty:
    st.info("No jobs yet.")
else:
    status_counts = (
        jobs.groupby("status", dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
    )
    st.bar_chart(status_counts.set_index("status"))

# ---------- Outreach by outcome ----------
st.subheader("Outreach by outcome")
if events.empty:
    st.info("No outreach yet.")
else:
    outcome_counts = (
        events.groupby("outcome")
              .size()
              .reset_index(name="count")
              .sort_values("count", ascending=False)
    )
    st.bar_chart(outcome_counts.set_index("outcome"))

# ---------- Channel performance ----------
st.subheader("Channel performance (rate of positive outcomes)")
if events.empty:
    st.info("No outreach yet.")
else:
    channel_perf = (
        events.assign(success=events["outcome"].map(is_success))
              .groupby("channel", dropna=False)
              .agg(sent=("event_id", "count"), success=("success", "sum"))
              .reset_index()
    )
    channel_perf["success_rate"] = (channel_perf["success"] / channel_perf["sent"]).round(3)
    st.dataframe(channel_perf, use_container_width=True)

# ---------- Template performance ----------
st.subheader("Template performance")
if events.empty:
    st.info("No outreach yet.")
else:
    tmpl_perf = (
        events.assign(success=events["outcome"].map(is_success))
              .groupby("template_name", dropna=False)
              .agg(sent=("event_id", "count"), success=("success", "sum"))
              .reset_index()
    )
    tmpl_perf["success_rate"] = (tmpl_perf["success"] / tmpl_perf["sent"]).round(3)
    tmpl_perf = tmpl_perf.sort_values("success_rate", ascending=False)
    st.dataframe(tmpl_perf, use_container_width=True)

# ---------- Company x Outcome heatmap ----------
st.subheader("Company × Outcome heatmap")
if events.empty or jobs.empty:
    st.info("Need jobs and outreach to draw heatmap.")
else:
    # attach company to events via job_id
    jj = jobs[["job_id", "company"]]
    ev_join = events.merge(jj, how="left", on="job_id")
    mat = ev_join.pivot_table(
        index="company", columns="outcome",
        values="event_id", aggfunc="count", fill_value=0
    )

    st.dataframe(mat, use_container_width=True)

    fig, ax = plt.subplots(
        figsize=(
            min(12, 1.5 * max(1, len(mat.columns)) + 4),
            min(0.6 * max(1, len(mat.index)) + 3, 12)
        )
    )
    im = ax.imshow(mat.values, aspect="auto")
    ax.set_xticks(np.arange(len(mat.columns)), labels=mat.columns)
    ax.set_yticks(np.arange(len(mat.index)), labels=mat.index)
    ax.set_xlabel("Outcome")
    ax.set_ylabel("Company")

    vmax = im.get_array().max() if im.get_array().size else 1
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            val = int(mat.iloc[i, j])
            ax.text(
                j, i, str(val),
                ha="center", va="center", fontsize=9,
                color=("white" if val > vmax / 2 else "black")
            )
    st.pyplot(fig, clear_figure=True)

st.markdown("---")

# ---------- Downloads ----------
st.subheader("Export raw tables")
colA, colB, colC = st.columns(3)
colA.download_button("Download jobs.csv", data=jobs.to_csv(index=False), file_name="jobs.csv", mime="text/csv")
colB.download_button("Download outreach_events.csv", data=events.to_csv(index=False), file_name="outreach_events.csv", mime="text/csv")
colC.download_button("Download contacts.csv", data=contacts.to_csv(index=False), file_name="contacts.csv", mime="text/csv")
