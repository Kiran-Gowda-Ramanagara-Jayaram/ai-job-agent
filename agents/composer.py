# agents/composer.py
import os, pathlib, json, re
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()  # reads OPENAI_API_KEY from .env

def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Try the unified Responses API; if unavailable in this SDK, fall back to Chat Completions.
    Returns plain text.
    """
    # Try unified Responses API
    try:
        rsp = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
        )
        return rsp.output_text
    except Exception:
        # Fallback to Chat Completions
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
        )
        return rsp.choices[0].message.content

def _extract_json_block(text: str):
    """
    Extract a JSON object from the LLM text. Supports ```json ...``` blocks or bare JSON.
    """
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S | re.I)
    if not m:
        m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1) if m.lastindex else m.group(0))
    except Exception:
        return None

def compose_artifacts(job, base_resume_md: str, rag_snippets: list, out_dir: str):
    """
    Creates:
      - tailored_resume_section.md
      - cover_letter.md
    Returns file paths + parsed JSON payload.
    """
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
    ctx = "\n\n".join(rag_snippets or [])

    system_prompt = "You are a precise career assistant. Be specific, honest, and concise."
    user_prompt = f"""
JOB TITLE: {job.title}
COMPANY: {job.company}
LOCATION: {job.location}

JOB DESCRIPTION:
{job.jd_text}

CONTEXT (company/JD snippets):
{ctx}

BASE RESUME MARKDOWN:
{base_resume_md}

TASKS:
1) Produce a tailored 6-10 bullet resume section that maps directly to JD must-haves (no fabrication).
2) Produce a 180-250 word cover letter referencing 1-2 company-specific details from CONTEXT.
3) Return JSON with keys: resume_bullets (array of strings), cover_letter (string).
"""

    text = _call_llm(system_prompt, user_prompt)
    data = _extract_json_block(text) or {"resume_bullets": [], "cover_letter": text.strip()}

    resume_path = os.path.join(out_dir, "tailored_resume_section.md")
    cl_path = os.path.join(out_dir, "cover_letter.md")

    with open(resume_path, "w") as f:
        bullets = data.get("resume_bullets", [])
        f.write("\n".join(f"- {b}" for b in bullets))

    with open(cl_path, "w") as f:
        f.write((data.get("cover_letter") or "").strip())

    return resume_path, cl_path, data
