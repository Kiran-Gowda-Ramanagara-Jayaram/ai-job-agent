# agents/star_agent.py
import os, pathlib
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()  # reads OPENAI_API_KEY from .env

def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Try Responses API; if not available, fall back to Chat Completions."""
    try:
        rsp = client.responses.create(
            model="gpt-4o-mini",
            input=[{"role": "system", "content": system_prompt},
                   {"role": "user", "content": user_prompt}],
            temperature=0.4,
        )
        return rsp.output_text
    except Exception:
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
            temperature=0.4,
        )
        return rsp.choices[0].message.content

def build_star_pack(company: str, title: str, jd_text: str,
                    base_resume_md: str, ctx_snippets: list, out_dir: str) -> str:
    """
    Generates artifacts/<company>_<title>/star_pack.md and returns its path.
    Produces 20 STAR question/answers tailored to the JD and the resume.
    """
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
    ctx = "\n\n".join(ctx_snippets or [])

    sys = (
        "You are an expert interview coach. Generate STAR (Situation, Task, Action, Result) "
        "answers that STRICTLY reflect the candidate's resume. Do NOT invent employers, dates, or tools. "
        "If a detail is unclear, keep it generic (e.g., <team>, <dataset>) rather than fabricating."
    )

    user = f"""
COMPANY: {company}
ROLE: {title}

JOB DESCRIPTION:
{jd_text}

COMPANY/JD CONTEXT SNIPPETS (optional):
{ctx}

CANDIDATE RESUME (Markdown):
{base_resume_md}

TASK:
- Create EXACTLY 20 question/answer pairs that a {title} interview would ask (mix technical + behavioral).
- For each pair, output in this Markdown structure:

### Q<n>. <question>
**S:** <1-2 sentences about the situation from the resume>
**T:** <what you needed to achieve>
**A:** <3-5 concise bullets about what you did — tools, methods, decisions>
**R:** <1-2 sentences with measurable impact/outcome>
**Why it maps to JD:** <1 sentence tying to a JD must-have>

RULES:
- Only use facts implied by the resume/projects. No fabricated company names or dates.
- Prefer examples that match the JD (tools/skills/impact). Reuse strong projects with different angles if needed.
- Keep answers tight and specific (avoid fluff). Use metrics where present; otherwise describe outcome qualitatively.
- Return a single Markdown document containing all 20 pairs.
"""

    md = _call_llm(sys, user).strip()
    path = os.path.join(out_dir, "star_pack.md")
    with open(path, "w") as f:
        f.write(md)
    return path
