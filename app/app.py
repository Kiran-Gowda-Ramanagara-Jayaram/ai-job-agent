# app/app.py

from pathlib import Path
import os, sys, json, csv, zipfile, io
from io import BytesIO, StringIO
from datetime import datetime

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import networkx as nx

# Core models/agents
from db.models import Session, JobPosting, FitScore, Artifact
from agents.composer import compose_artifacts
from agents.prep_agent import build_prep_pack
from agents.star_agent import build_star_pack as build_star_qas
from agents.outreach_agent import draft_outreach, ALL_TEMPLATES
from agents.gap_agent import build_skill_gap_plan                     # (B)
from agents.coach_agent import transcribe_and_score                    # (F)
from agents.rolefit import rolefit_score                               # (D)
from utils.docx_resume import build_ats_docx                           # (E)
from rag.store import SimpleStore

# CRM
from db.crm import Session as CRMSession, Contact, OutreachEvent, init_crm

# Bandit (learning loop)
from db.bandit import init_bandit, update_stat, reward_from_outcome

# Hunter.io (optional)
try:
    from integrations.hunter import domain_search, email_finder, verify_email, HunterError
    HUNTER_AVAILABLE = True
except Exception:
    HUNTER_AVAILABLE = False
    class HunterError(Exception): ...
HUNTER_API_SET = bool(os.getenv("HUNTER_API_KEY"))

# --------------------------------------------------------------------------------------
st.set_page_config(page_title="AI Job Agent", layout="wide")

def _load_base_resume() -> str:
    return Path("data/base_resume.md").read_text()

def _company_contacts(company: str, limit: int = 8):
    cs = CRMSession()
    return (
        cs.query(Contact)
        .filter(Contact.company.ilike(f"%{company}%"))
        .order_by(Contact.created_at.desc())
        .limit(limit)
        .all()
    )

def _job_outreach(job_id, limit: int = 10):
    cs = CRMSession()
    return (
        cs.query(OutreachEvent)
        .filter_by(job_id=str(job_id))
        .order_by(OutreachEvent.id.desc())
        .limit(limit)
        .all()
    )

def _key(job_id: int, name: str) -> str:
    return f"{name}_{job_id}"

def _get_state(job_id: int, name: str, default=None):
    return st.session_state.get(_key(job_id, name), default)

def _set_state(job_id: int, name: str, value):
    st.session_state[_key(job_id, name)] = value

def _export_job_packet(job):
    adir = f"artifacts/{job.company}_{job.title}".replace(" ", "_")
    resume_p = Path(adir) / "tailored_resume_section.md"
    cover_p  = Path(adir) / "cover_letter.md"
    prep_p   = Path(adir) / "prep_pack.md"
    star_p   = Path(adir) / "star_pack.md"
    ats_p    = Path(adir) / "ATS_resume.docx"

    cs = CRMSession()
    contacts = (
        cs.query(Contact)
        .filter(Contact.company.ilike(f"%{job.company}%"))
        .order_by(Contact.created_at.desc())
        .all()
    )
    evs = (
        cs.query(OutreachEvent)
        .filter_by(job_id=str(job.id))
        .order_by(OutreachEvent.id.desc())
        .all()
    )

    buf = BytesIO()
    z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)

    if resume_p.exists(): z.write(resume_p, arcname=f"{adir}/tailored_resume_section.md")
    if cover_p.exists():  z.write(cover_p,  arcname=f"{adir}/cover_letter.md")
    if prep_p.exists():   z.write(prep_p,   arcname=f"{adir}/prep_pack.md")
    if star_p.exists():   z.write(star_p,   arcname=f"{adir}/star_pack.md")
    if ats_p.exists():    z.write(ats_p,    arcname=f"{adir}/ATS_resume.docx")

    meta = {
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "status": job.status,
        "posted_at": str(job.posted_at),
    }
    z.writestr(f"{adir}/job_meta.json", json.dumps(meta, indent=2))
    z.writestr(f"{adir}/job_description.txt", (job.jd_text or "").strip())

    cbuf = StringIO(); cw = csv.writer(cbuf)
    cw.writerow(["name","email","title","company","linkedin_url","source","id"])
    for c in contacts:
        cw.writerow([c.name or "", c.email or "", c.title or "", c.company or "", c.linkedin_url or "", c.source or "", c.id])
    z.writestr(f"{adir}/crm_contacts.csv", cbuf.getvalue())

    obuf = StringIO(); ow = csv.writer(obuf)
    ow.writerow(["id","channel","template_name","outcome","notes","contact_id"])
    for e in evs:
        ow.writerow([e.id, e.channel or "", e.template_name or "", e.outcome or "", e.notes or "", e.contact_id])
    z.writestr(f"{adir}/outreach_events.csv", obuf.getvalue())

    z.close()
    buf.seek(0)
    fname = f"{job.company}_{job.title}_packet_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.zip".replace(" ", "_")
    return buf.read(), fname

def guess_domains(company: str):
    base = (company or "").lower().replace(" ", "")
    candidates = [
        f"{base}.com", f"{base}.co", f"{base}.ai", f"{base}.io", f"{base}.so",
        f"make{base}.com", f"get{base}.com", f"join{base}.com", f"team{base}.com",
    ]
    special = {
        "notion": ["makenotion.com", "notion.so"],
        "openai": ["openai.com"],
        "stripe": ["stripe.com"],
        "databricks": ["databricks.com"],
        "pinterest": ["pinterest.com"],
    }
    candidates = special.get(base, []) + candidates
    seen, ordered = set(), []
    for d in candidates:
        if d not in seen:
            seen.add(d); ordered.append(d)
    return ordered

# --------------------------------------------------------------------------------------
def render_queue():
    st.title("📬 Applications Queue")

    s_for_kpis = Session()
    all_jobs = s_for_kpis.query(JobPosting).all()
    status_counts = pd.Series([j.status or "new" for j in all_jobs]).value_counts()
    total_contacts = CRMSession().query(Contact).count()
    total_outreach = CRMSession().query(OutreachEvent).count()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Jobs in queue", len(all_jobs))
    m2.metric("Contacts saved", total_contacts)
    m3.metric("Outreach logged", total_outreach)
    m4.metric("Applied", int(status_counts.get("applied", 0)))

    with st.expander("➕ Add a real job (paste JD)"):
        with st.form("add_job_form"):
            c1, c2, c3 = st.columns(3)
            company  = c1.text_input("Company", placeholder="e.g., Databricks")
            title    = c2.text_input("Title", placeholder="e.g., Machine Learning Engineer")
            location = c3.text_input("Location", placeholder="e.g., Remote - USA")
            jd_text  = st.text_area("Job description (paste full JD)", height=220)
            if st.form_submit_button("Add to queue"):
                if not (company and title and jd_text):
                    st.warning("Please fill Company, Title, and paste the Job description.")
                else:
                    with st.spinner("Adding job to queue…"):
                        s2 = Session()
                        s2.add(JobPosting(
                            company=company.strip(),
                            title=title.strip(),
                            location=(location or "").strip(),
                            jd_text=jd_text.strip(),
                            posted_at=datetime.utcnow(),
                            status="new",
                        ))
                        s2.commit()
                    st.toast("Job added to queue ✅")
                    st.rerun()

    if st.button("📊 Open Dashboard"):
        st.session_state["_page"] = "Dashboard"; st.rerun()

    init_crm(); init_bandit()

    s = Session()
    jobs = s.query(JobPosting).order_by(JobPosting.posted_at.desc()).all()
    if not jobs:
        st.info("No jobs yet. Add one above or run an ingest script.")
        return

    for j in jobs:
        fs = (
            s.query(FitScore)
            .filter_by(job_id=j.id)
            .order_by(FitScore.created_at.desc())
            .first()
        )
        score = f"{fs.total:.2f}" if fs else "—"

        with st.expander(f"{j.company} — {j.title}  |  {j.location}  |  score: {score}  |  status: {j.status}"):
            st.markdown("**Job description**")
            st.code((j.jd_text or "").strip(), language="markdown")

            tab_art, tab_prep, tab_star, tab_coach, tab_hunter, tab_contacts, tab_activity = st.tabs([
                "📄 Artifacts", "🧠 Prep", "⭐ STAR", "🎙️ Coach", "🔎 Recruiters", "📧 Contacts & Outreach", "📊 Activity"
            ])

            # --- Artifacts ---
            with tab_art:
                # RoleFit v2 probability (if model trained)
                p = rolefit_score(j.jd_text or "", _load_base_resume())
                if p is not None:
                    st.metric("RoleFit v2 (probability)", f"{p:.2f}")
                    st.progress(int(p*100))
                else:
                    st.caption("Tip: train RoleFit v2 → `python -m scripts.train_fit_model`")

                art = (
                    s.query(Artifact)
                    .filter_by(job_id=j.id)
                    .order_by(Artifact.created_at.desc())
                    .first()
                )
                if art:
                    st.markdown("**Tailored resume bullets**")
                    tailored_md = Path(art.resume_path).read_text()
                    st.code(tailored_md, language="markdown")
                    st.markdown("**Cover letter**")
                    st.code(Path(art.cover_letter_path).read_text(), language="markdown")

                    # ATS DOCX export
                    if st.button("Generate ATS .docx", key=f"ats_{j.id}"):
                        out_dir = f"artifacts/{j.company}_{j.title}".replace(" ", "_")
                        docx_path = build_ats_docx(j.company, j.title, tailored_md, _load_base_resume(), out_dir)
                        st.success("ATS .docx ready.")
                        with open(docx_path, "rb") as f:
                            st.download_button("⬇️ Download ATS_resume.docx", f.read(),
                                               file_name="ATS_resume.docx",
                                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                               key=f"dl_ats_{j.id}")
                else:
                    if st.button("Generate artifacts for this job", key=f"gen_{j.id}"):
                        progress = st.progress(0)
                        with st.spinner("Composing tailored materials…"):
                            store = SimpleStore(); store.add_texts([j.jd_text, f"{j.company} — {j.title}"])
                            progress.progress(25)
                            ctx = store.search(f"{j.company} {j.title}", k=3)
                            progress.progress(60)
                            out_dir = f"artifacts/{j.company}_{j.title}".replace(" ", "_")
                            resume_p, cl_p, payload = compose_artifacts(j, _load_base_resume(), ctx, out_dir)
                            progress.progress(100)
                            s.add(Artifact(job_id=j.id, resume_path=resume_p, cover_letter_path=cl_p, qa_json=payload))
                            s.commit()
                        st.toast("Artifacts generated ✅")
                        st.rerun()

                packet = st.button("⬇️ Download job packet (ZIP)", key=f"zip_{j.id}")
                if packet:
                    data, fname = _export_job_packet(j)
                    st.download_button("Download", data, file_name=fname, mime="application/zip", key=f"dl_{j.id}")

                c1, c2 = st.columns(2)
                if c1.button("Mark as applied", key=f"ap_{j.id}"):
                    j.status = "applied"; s.commit(); st.toast("Marked as applied ✅")
                if c2.button("Skip", key=f"s_{j.id}"):
                    j.status = "skipped"; s.commit(); st.toast("Skipped")

            # --- Prep ---
            with tab_prep:
                prep_dir = f"artifacts/{j.company}_{j.title}".replace(" ", "_")
                prep_path = Path(prep_dir) / "prep_pack.md"
                if st.button("Generate prep pack", key=f"prep_{j.id}"):
                    progress = st.progress(0)
                    with st.spinner("Building interview prep pack…"):
                        store = SimpleStore(); store.add_texts([j.jd_text, f"{j.company} — {j.title}"])
                        progress.progress(35)
                        ctx = store.search(f"{j.company} {j.title} product news mission values", k=5)
                        progress.progress(70)
                        path = build_prep_pack(j.company, j.title, j.jd_text, ctx, prep_dir)
                        progress.progress(100)
                    st.toast("Prep pack generated ✅")
                    st.code(Path(path).read_text(), language="markdown")
                elif prep_path.exists():
                    st.code(prep_path.read_text(), language="markdown")
                else:
                    st.info("No prep pack yet.")

                st.markdown("**Skill Gap Tutor (7-day plan)**")
                if st.button("Generate skill-gap plan", key=f"gap_{j.id}"):
                    with st.spinner("Analyzing JD vs resume and drafting your 7-day plan…"):
                        plan = build_skill_gap_plan(j.company, j.title, j.jd_text, _load_base_resume())
                    st.success("Skill-gap plan ready.")
                    st.code(plan, language="markdown")

            # --- STAR ---
            with tab_star:
                star_dir = f"artifacts/{j.company}_{j.title}".replace(" ", "_")
                star_path = Path(star_dir) / "star_pack.md"
                if st.button("Generate 20 STAR answers", key=f"star_{j.id}"):
                    progress = st.progress(0)
                    with st.spinner("Drafting role-specific STAR answers…"):
                        store = SimpleStore(); store.add_texts([j.jd_text, f"{j.company} — {j.title}"])
                        progress.progress(40)
                        ctx = store.search(f"{j.company} {j.title} interview questions topics", k=5)
                        progress.progress(80)
                        path = build_star_qas(j.company, j.title, j.jd_text, _load_base_resume(), ctx, star_dir)
                        progress.progress(100)
                    st.toast("STAR pack generated ✅")
                    st.code(Path(path).read_text(), language="markdown")
                elif star_path.exists():
                    st.code(star_path.read_text(), language="markdown")
                else:
                    st.info("No STAR pack yet.")

            # --- Coach (Audio) ---
            with tab_coach:
                st.markdown("**Upload a short answer (30–120s) to a typical interview question**")
                audio = st.file_uploader("Upload audio (wav/mp3/m4a)", type=["wav","mp3","m4a"], key=f"au_{j.id}")
                if audio is not None:
                    st.audio(audio)
                if st.button("Transcribe + Score", key=f"coach_{j.id}"):
                    if not audio:
                        st.warning("Please upload audio first.")
                    else:
                        with st.spinner("Transcribing and scoring…"):
                            res = transcribe_and_score(audio.read(), audio.name, j.company, j.title, j.jd_text, _load_base_resume())
                        st.success("Coaching report ready.")
                        with st.expander("Transcript", expanded=False):
                            st.write(res["transcript"])
                        st.code(res["report"], language="markdown")
                        # A little celebration if strong result keyword
                        if "9/10" in res["report"] or "10/10" in res["report"]:
                            st.balloons()

            # --- Hunter (recruiters) ---
            with tab_hunter:
                st.markdown("**Find recruiter emails (Hunter.io — work emails only)**")
                if not HUNTER_AVAILABLE:
                    st.info("Hunter integration not installed. Create integrations/hunter.py and set HUNTER_API_KEY in .env to enable.")
                elif not HUNTER_API_SET:
                    st.info("Set HUNTER_API_KEY in your .env to use Hunter.io lookups.")
                else:
                    guesses = guess_domains(j.company)
                    default_domain = guesses[0] if guesses else ((j.company or '').lower().replace(' ', '') + '.com')
                    domain = st.text_input("Company domain (e.g., stripe.com)", value=default_domain, key=f"dom_{j.id}")
                    dept = st.selectbox(
                        "Department filter",
                        ["hr","communication","marketing","it","management","sales","legal","finance","support","executive","(any)"],
                        index=0, key=f"dept_{j.id}"
                    )
                    b1, b2 = st.columns(2)
                    if b1.button("Domain search (HR/Recruiting)", key=f"h_dom_{j.id}"):
                        try:
                            rows = domain_search(domain, department=None if dept == "(any)" else dept, limit=10)
                            _set_state(j.id, "hunter_rows", rows or []); _set_state(j.id, "hunter_error", None)
                        except HunterError as e:
                            _set_state(j.id, "hunter_rows", []); _set_state(j.id, "hunter_error", str(e))

                    if b2.button("Smart search (try common domains)", key=f"h_smart_{j.id}"):
                        rows_all = []
                        with st.spinner("Trying common domains…"):
                            for d in guesses:
                                try:
                                    r = domain_search(d, department=None if dept == "(any)" else dept, limit=6) or []
                                    rows_all.extend(r)
                                except HunterError:
                                    pass
                        _set_state(j.id, "hunter_rows", rows_all)
                        _set_state(j.id, "hunter_error", None if rows_all else "No results across common domains")

                    err = _get_state(j.id, "hunter_error")
                    if err: st.error(f"Hunter error: {err}")

                    rows = _get_state(j.id, "hunter_rows", [])
                    if rows:
                        st.write("**Results:**")
                        for idx, r in enumerate(rows):
                            st.write(
                                f"- {r.get('first_name','')} {r.get('last_name','')} — "
                                f"{r.get('position') or 'Recruiting'} — "
                                f"{r.get('email')} (confidence {r.get('confidence')})"
                            )
                            if st.button(f"Save {r.get('email')}", key=f"save_{j.id}_{idx}"):
                                if not r.get("email"):
                                    st.warning("This entry has no email; not saved.")
                                else:
                                    cs3 = CRMSession()
                                    cs3.add(Contact(
                                        name=f"{r.get('first_name','')} {r.get('last_name','')}".strip() or None,
                                        title=r.get('position') or "Recruiter",
                                        company=j.company or r.get('company'),
                                        email=r.get('email'),
                                        linkedin_url=r.get('linkedin'),
                                        source="hunter_domain"
                                    ))
                                    cs3.commit()
                                    st.toast("Saved to CRM ✅")
                    else:
                        st.caption("No cached Hunter results yet. Run a search above.")

                    with st.form(f"h_finder_{j.id}"):
                        st.caption("Know a recruiter's name? Find their work email:")
                        fn, ln = st.columns(2)
                        first = fn.text_input("First name")
                        last  = ln.text_input("Last name")
                        dom   = st.text_input("Domain (e.g., stripe.com)", value=domain)
                        go = st.form_submit_button("Find + verify")
                        if go:
                            try:
                                res = email_finder(dom, first, last, j.company)
                                email = res.get("email")
                                payload = {"first": first, "last": last, "domain": dom, "res": res}
                                if email:
                                    payload["verify"] = verify_email(email)
                                _set_state(j.id, "finder_payload", payload)
                            except HunterError as e:
                                _set_state(j.id, "finder_payload", {"error": str(e)})

                    fpayload = _get_state(j.id, "finder_payload")
                    if fpayload:
                        if "error" in fpayload:
                            st.error(f"Hunter error: {fpayload['error']}")
                        else:
                            email = fpayload.get("res", {}).get("email")
                            score = fpayload.get("res", {}).get("score")
                            ver   = fpayload.get("verify")
                            if email:
                                ver_txt = f" | Verify: {ver['result']} ({ver.get('score')})" if ver else ""
                                st.success(f"Found: {email} (finder score {score}){ver_txt}")
                                if st.button("Save to CRM", key=f"savefinder_{j.id}_{email}"):
                                    cs4 = CRMSession()
                                    cs4.add(Contact(
                                        name=f"{fpayload['first']} {fpayload['last']}",
                                        title="Recruiter",
                                        company=j.company,
                                        email=email,
                                        linkedin_url=None,
                                        source="hunter_finder"
                                    ))
                                    cs4.commit()
                                    st.toast("Saved to CRM ✅")
                            else:
                                st.info("No email found for that name/domain.")

            # --- Contacts & Outreach ---
            with tab_contacts:
                st.caption("Saved contacts for this company:")
                contacts_under = _company_contacts(j.company)
                if contacts_under:
                    for c in contacts_under:
                        col_a, col_b, col_c = st.columns([4,1,1])
                        with col_a:
                            ll = f" — {c.linkedin_url}" if c.linkedin_url else ""
                            st.write(f"- {c.name or '—'} ({c.title or '—'}) — {c.email or '—'}{ll}")
                        open_key = f"draft_open_{c.id}"
                        payload_key = f"draft_payload_{c.id}"
                        toast_key = f"draft_toast_{c.id}"
                        with col_b:
                            if st.button("Draft outreach", key=f"out_h_{j.id}_{c.id}"):
                                _set_state(j.id, open_key, True)
                                _set_state(
                                    j.id,
                                    payload_key,
                                    draft_outreach(
                                        j.company, j.title, j.jd_text,
                                        c.name or "", c.title or "", _load_base_resume()
                                    ),
                                )
                        with col_c:
                            if st.button("Delete", key=f"del_h_{j.id}_{c.id}"):
                                csd = CRMSession(); obj = csd.get(Contact, c.id)
                                if obj: csd.delete(obj); csd.commit()
                                st.toast("Deleted contact")

                        if _get_state(j.id, open_key, False):
                            draft = _get_state(j.id, payload_key) or {}
                            st.markdown("**Email subject**"); st.code(draft.get("email_subject",""))
                            st.markdown("**Email body**");    st.code(draft.get("email_body",""))
                            st.markdown("**LinkedIn DM**");   st.code(draft.get("linkedin_dm","") or "(empty)")

                            with st.form(f"log_out_h_{j.id}_{c.id}"):
                                ch = st.selectbox("Channel", ["email","linkedin","portal"], index=0)
                                tmpl_default = draft.get("template_used", ALL_TEMPLATES[0])
                                tmpl = st.selectbox("Template used", ALL_TEMPLATES, index=ALL_TEMPLATES.index(tmpl_default))
                                notes = st.text_area("Notes (optional)")
                                if st.form_submit_button("Log outreach as sent"):
                                    try:
                                        evs = CRMSession()
                                        ev = OutreachEvent(
                                            contact_id=c.id, job_id=str(j.id),
                                            channel=ch, template_name=tmpl,
                                            outcome="sent", notes=notes
                                        )
                                        evs.add(ev); evs.commit()
                                        _set_state(j.id, toast_key, "ok")
                                    except Exception as e:
                                        _set_state(j.id, toast_key, f"err:{e}")

                            toast = _get_state(j.id, toast_key)
                            if toast == "ok":
                                st.toast("Outreach logged ✅")
                            elif toast and str(toast).startswith("err:"):
                                st.error(f"Failed to log outreach: {str(toast)[4:]}")

            # --- Activity ---
            with tab_activity:
                st.caption("Recent outreach for this job:")
                events = _job_outreach(j.id)
                if events:
                    for ev in events:
                        st.write(f"- [id#{ev.id}] {ev.channel} → {ev.template_name} — outcome: {ev.outcome or '—'} — notes: {ev.notes or '—'}")
                    most_recent = events[0]
                    oc1, oc2 = st.columns([3,1])
                    with oc1:
                        outcome = st.selectbox(
                            "Outcome",
                            ["sent","no_reply","positive_reply","interview","rejected"],
                            index=["sent","no_reply","positive_reply","interview","rejected"].index(most_recent.outcome or "sent"),
                            key=f"oc_{j.id}"
                        )
                    with oc2:
                        if st.button("Save", key=f"save_out_{j.id}"):
                            cs = CRMSession()
                            row = cs.get(OutreachEvent, most_recent.id)
                            if row:
                                row.outcome = outcome; cs.commit()
                                bucket = f"role:{(j.title or '').lower()}|company:{(j.company or '').lower()}"
                                update_stat(bucket, row.template_name or ALL_TEMPLATES[0], reward_from_outcome(outcome))
                                st.toast("Outcome saved + model updated ✅")
                                if outcome in ("positive_reply", "interview"):
                                    st.balloons()
                            else:
                                st.error("Could not load event to save.")

def render_dashboard():
    st.title("📊 AI Job Agent — Dashboard")

    if st.button("📋 Back to Queue"):
        st.session_state["_page"] = "Queue"; st.rerun()

    js = Session().query(JobPosting).all()
    cs = CRMSession()
    evs = cs.query(OutreachEvent).all()
    contacts = cs.query(Contact).all()

    total_jobs = len(js)
    total_contacts = len(contacts)
    total_outreach = len(evs)
    interviews = sum(1 for e in evs if e.outcome == "interview")
    positives  = sum(1 for e in evs if e.outcome == "positive_reply")

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Jobs tracked", total_jobs)
    k2.metric("Contacts", total_contacts)
    k3.metric("Outreach", total_outreach)
    k4.metric("Interviews", interviews)
    k5.metric("Positive replies", positives)

    if evs:
        df_out = pd.Series([e.outcome or "sent" for e in evs], name="count").value_counts().rename_axis("outcome").reset_index()
        df_out = df_out.rename(columns={"count":"value"})
        st.subheader("Outcomes (overall)")
        st.bar_chart(df_out, x="outcome", y="value", use_container_width=True)

        job_map = {str(j.id): (j.company or "—") for j in js}
        comp_pairs = []
        for e in evs:
            comp = job_map.get(str(e.job_id), "—")
            comp_pairs.append((comp, e.outcome or "sent"))
        df_comp = pd.DataFrame(comp_pairs, columns=["company","outcome"])
        top = (
            df_comp[df_comp["outcome"].isin(["interview","positive_reply"])]
            .groupby("company").size().reset_index(name="wins")
            .sort_values("wins", ascending=False).head(12)
        )
        st.subheader("Top companies (interviews + positive replies)")
        if not top.empty:
            st.bar_chart(top, x="company", y="wins", use_container_width=True)
        else:
            st.info("No wins yet. Log outcomes on the Queue page.")
    else:
        st.info("No outreach events yet. Log some outreach from the Queue.")

    st.markdown("---")
    st.subheader("Recruiter Network (beta)")
    G = nx.Graph()
    for c in contacts:
        comp = (c.company or "—").strip()
        G.add_node(comp, type="company")
        label = c.name or c.email or "Contact"
        G.add_node(f"contact:{c.id}", type="contact", label=label)
        G.add_edge(comp, f"contact:{c.id}", weight=1)
    pos = nx.spring_layout(G, k=0.7, seed=42)
    fig, ax = plt.subplots(figsize=(8, 6))
    nx.draw_networkx_nodes(G, pos,
        nodelist=[n for n,d in G.nodes(data=True) if d.get("type")=="company"],
        node_color="#22c55e", node_size=800, alpha=0.9, ax=ax)
    nx.draw_networkx_nodes(G, pos,
        nodelist=[n for n,d in G.nodes(data=True) if d.get("type")=="contact"],
        node_color="#3b82f6", node_size=500, alpha=0.8, ax=ax)
    labels = {n: (d.get("label") if d.get("type")=="contact" else n) for n,d in G.nodes(data=True)}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=9, ax=ax)
    nx.draw_networkx_edges(G, pos, edge_color="#7aa2f7", width=1.5, alpha=0.7, ax=ax)
    ax.axis("off")
    st.pyplot(fig, clear_figure=True)

# --------------------------------------------------------------------------------------
if "_page" not in st.session_state:
    st.session_state["_page"] = "Queue"

with st.sidebar:
    st.header("Navigation")
    choice = st.radio("Go to", ["Queue", "Dashboard"], index=0 if st.session_state["_page"]=="Queue" else 1)
    if choice != st.session_state["_page"]:
        st.session_state["_page"] = choice
        st.rerun()

init_crm()
init_bandit()

if st.session_state["_page"] == "Queue":
    render_queue()
else:
    render_dashboard()
