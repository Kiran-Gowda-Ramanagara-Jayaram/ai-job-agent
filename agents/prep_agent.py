# agents/prep_agent.py
import os, pathlib
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()  # reads OPENAI_API_KEY from .env

def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Try Responses API; if not present in this SDK, fall back to Chat Completions."""
    try:
        rsp = client.responses.create(
            model="gpt-4o-mini",
            input=[{"role":"system","content":system_prompt},
                   {"role":"user","content":user_prompt}],
            temperature=0.4,
        )
        return rsp.output_text
    except Exception:
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":system_prompt},
                      {"role":"user","content":user_prompt}],
            temperature=0.4,
        )
        return rsp.choices[0].message.content

def build_prep_pack(company: str, title: str, jd_text: str, ctx_snippets: list, out_dir: str) -> str:
    """
    Generates artifacts/<company>_<title>/prep_pack.md and returns its path.
    """
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
    ctx = "\n\n".join(ctx_snippets or [])

    sys = "You are a concise interview prep coach for tech roles. Be specific and recent."
    user = f"""
Company: {company}
Role: {title}

Job Description:
{jd_text}

Context snippets (about/product/news if available):
{ctx}

Produce a Markdown pack with these sections:
1) Likely Interview Questions — 5 technical + 5 behavioral. For each, add 2–3 bullet points of what a strong answer covers.
2) Talking Points — 6 company/product facts (<=25 words each) that are safe to mention.
3) Competitors & Differentiators — 3 competitors/categories with 1 differentiator each.
4) Flashcards — 5 Q→A pairs (short) for quick review.

Keep it under ~500–700 words total. Avoid fluff.
"""
    md = _call_llm(sys, user)
    path = os.path.join(out_dir, "prep_pack.md")
    with open(path, "w") as f:
        f.write(md.strip())
    return path
