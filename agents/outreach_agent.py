# agents/outreach_agent.py
from __future__ import annotations
import os, json, re
from typing import Dict
from openai import OpenAI
from db.bandit import pick_template

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Outreach template styles (options the bandit will choose among)
TEMPLATES = {
    "ai_personalized_v1": (
        "Tone: warm, concise, credible. 2 short paragraphs + 3 bullets. "
        "Personalize with 1–2 company details from the JD. Map 1 resume achievement to the role."
    ),
    "ai_value_prop_v1": (
        "Tone: business-impact. Open on team goal + how I improve it. "
        "1 paragraph + 3 bullets focused on outcomes (latency, cost, accuracy). Include a concrete metric."
    ),
    "ai_concise_v1": (
        "Tone: ultra-brief mobile-first. Max 3 sentences + 2 bullets. "
        "No fluff; include exactly one quantified result."
    ),
}
ALL_TEMPLATES = list(TEMPLATES.keys())

def _json_from_text(text: str) -> Dict[str, str]:
    """Parse model output into {email_subject, email_body, linkedin_dm}."""
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    subj, body, dm = "", text, ""
    m1 = re.search(r"(?i)email subject\s*:\s*(.+)", text)
    if m1: subj = m1.group(1).strip()
    m2 = re.search(r"(?i)email body\s*:\s*(.+?)(?:linkedin dm:|$)", text, flags=re.S)
    if m2: body = m2.group(1).strip()
    m3 = re.search(r"(?i)linkedin dm\s*:\s*(.+)$", text, flags=re.S)
    if m3: dm = m3.group(1).strip()
    return {"email_subject": subj, "email_body": body, "linkedin_dm": dm}

def draft_outreach(
    company: str,
    role_title: str,
    jd_text: str,
    contact_name: str,
    contact_title: str,
    base_resume_md: str,
    template: str | None = None,
) -> Dict[str, str]:
    """
    Create subject/body/DM tailored to JD + resume.
    Returns: {email_subject, email_body, linkedin_dm, template_used}
    """
    # If no template provided, let the bandit choose a default for this bucket
    bucket = f"role:{(role_title or '').lower()}|company:{(company or '').lower()}"
    chosen_template = template or pick_template(bucket, ALL_TEMPLATES)
    style = TEMPLATES[chosen_template]

    messages = [
        {
            "role": "system",
            "content": (
                "You draft recruiter outreach for a job seeker. "
                "Write crisp, professional copy that maps resume achievements to the role. "
                "Avoid exaggeration; keep facts consistent with the resume. "
                "Return ONLY JSON with keys: email_subject, email_body, linkedin_dm."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Template style: {chosen_template} — {style}\n\n"
                f"Company: {company}\nRole: {role_title}\n\n"
                "JD snippet (context; don't copy verbatim):\n"
                f"---\n{(jd_text or '')[:1800]}\n---\n\n"
                "Candidate resume (markdown):\n"
                f"---\n{(base_resume_md or '')[:3500]}\n---\n\n"
                f"Recruiter/Contact: {contact_name or '(unknown)'}  |  Title: {contact_title or '(unknown)'}\n\n"
                "Return JSON only, e.g.:\n"
                '{\n'
                '  "email_subject": "...",\n'
                '  "email_body": "Hi <name>, ...",\n'
                '  "linkedin_dm": "Hi <name>, ..."\n'
                "}\n"
            ),
        },
    ]

    # Prefer Responses API; fall back to Chat Completions
    text: str
    try:
        rsp = client.responses.create(model="gpt-4o-mini", input=messages, temperature=0.6)
        text = getattr(rsp, "output_text", "") or ""
        if not text and getattr(rsp, "output", None):
            for part in rsp.output or []:
                for c in getattr(part, "content", []) or []:
                    if getattr(c, "type", "") == "output_text":
                        text = getattr(c, "text", "") or ""
                        break
                if text:
                    break
    except Exception:
        rsp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, temperature=0.6)
        text = rsp.choices[0].message.content

    out = _json_from_text(text)
    out["template_used"] = chosen_template
    return out
