# agents/gap_agent.py
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM = """You are a career mentor. Given a job description (JD) and a candidate resume,
produce:
1) Top skill gaps (ranked), each with 2–3 concrete subskills.
2) A focused 7-day plan: daily goals, 1–2 reputable resources (no paywalls), and one hands-on micro-task per day.
3) 5 short interview practice prompts tailored to the gaps.
Keep it concise, actionable, US market-relevant, and realistic for a week."""

def build_skill_gap_plan(company: str, title: str, jd_text: str, resume_md: str) -> str:
    user = f"""Company: {company}
Role: {title}

[JOB DESCRIPTION]
{jd_text}

[RESUME]
{resume_md}"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system", "content": SYSTEM},
            {"role":"user", "content": user}
        ],
        temperature=0.4,
    )
    return resp.choices[0].message.content.strip()
