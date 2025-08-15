# agents/coach_agent.py
import os, io
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SCORE_SYSTEM = """You are an interview coach. Score the candidate's answer (transcript)
on a 1–10 scale across: Clarity, Structure (STAR), Technical Depth, Impact/Results,
Role Alignment, Conciseness. Then provide 3–5 concrete improvements and 2 follow-up questions.
Return a tidy markdown report."""

def transcribe_and_score(file_bytes: bytes, filename: str,
                         company: str, title: str, jd_text: str, resume_md: str) -> dict:
    # --- Transcribe (try gpt-4o-transcribe, fall back to whisper-1) ---
    audio_file = io.BytesIO(file_bytes); audio_file.name = filename
    try:
        tr = client.audio.transcriptions.create(model="gpt-4o-transcribe", file=audio_file)
        transcript = tr.text
    except Exception:
        audio_file.seek(0)
        tr = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
        transcript = getattr(tr, "text", None) or (tr.get("text") if isinstance(tr, dict) else "")

    # --- Score ---
    user = f"""Company: {company}
Role: {title}

[JD]
{jd_text}

[RESUME]
{resume_md}

[TRANSCRIPT]
{transcript}
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system", "content": SCORE_SYSTEM},
            {"role":"user", "content": user}
        ],
        temperature=0.3,
    )
    report = resp.choices[0].message.content.strip()
    return {"transcript": transcript, "report": report}
