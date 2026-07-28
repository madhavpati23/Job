"""Claude-backed resume tailoring and cover-letter writing.

The app works without an API key — `jobapply_mcp.drafting` still produces a
grounded scaffold, and the gap analysis below is pure Python. A key upgrades
both from "structured starting point" to "finished draft".
"""

from __future__ import annotations

import os
import re
from collections import Counter

MODEL = "claude-opus-5"

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.]{1,}")
_STOP = {
    "the", "and", "for", "with", "you", "our", "are", "will", "this", "that",
    "have", "your", "from", "but", "not", "all", "can", "has", "who", "job",
    "work", "team", "role", "company", "experience", "years", "requirements",
    "including", "across", "their", "they", "what", "how", "about", "were",
}


def keywords(text: str, n: int = 25) -> list[str]:
    toks = [w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP and len(w) > 2]
    return [w for w, _ in Counter(toks).most_common(n)]


def gap_analysis(resume: str, job_description: str, n: int = 25) -> dict[str, list[str]]:
    """Which posting keywords the resume already covers, and which it misses."""
    job_kw = keywords(job_description, n)
    resume_l = (resume or "").lower()
    return {
        "covered": [k for k in job_kw if k in resume_l],
        "missing": [k for k in job_kw if k not in resume_l],
    }


# --- Claude ---------------------------------------------------------------

def api_key(user_key: str = "") -> str:
    """Resolve a key from the user's input, Streamlit secrets, or the env."""
    if user_key.strip():
        return user_key.strip()
    try:
        import streamlit as st

        if "ANTHROPIC_API_KEY" in st.secrets:
            return str(st.secrets["ANTHROPIC_API_KEY"])
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


def available(user_key: str = "") -> bool:
    if not api_key(user_key):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _complete(system: str, prompt: str, key: str, max_tokens: int = 20000) -> str:
    """One streamed request to Claude. Returns the text, or raises RuntimeError."""
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    kwargs = dict(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    # Server-side fallbacks re-run the request on another model if Claude Opus 5's
    # safety classifiers decline it, so a borderline job posting can't dead-end the
    # user. Older SDKs don't know the parameter — fall back to a plain request.
    try:
        with client.beta.messages.stream(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
        ) as stream:
            message = stream.get_final_message()
    except (TypeError, AttributeError, anthropic.BadRequestError):
        with client.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError(
            "Claude declined this request. Try again with a different job posting."
        )
    text = "".join(b.text for b in message.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("Claude returned an empty response — try again.")
    return text


_TAILOR_SYSTEM = """You are an expert resume editor. You rewrite an existing resume so it \
targets one specific job posting.

Hard rules:
- Never invent employers, job titles, dates, degrees, certifications, or metrics. \
Every fact in your output must be traceable to the original resume.
- You may re-order, re-word, re-emphasize, merge, and cut. You may adopt the posting's \
vocabulary where it genuinely describes work the candidate already did.
- Surface the most relevant experience earliest. Cut or compress what the posting \
doesn't care about.
- Keep it ATS-friendly: plain markdown, standard section headings, no tables or columns.

Output the complete tailored resume in markdown and nothing else — no preamble, no \
commentary, no explanation of your changes."""


def tailor_resume(resume: str, job: dict, key: str, extra_notes: str = "") -> str:
    notes = f"\n\nAdditional instructions from the candidate:\n{extra_notes}" if extra_notes.strip() else ""
    prompt = f"""Tailor this resume for the job posting below.

<job_posting>
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}

{job.get('description', '')}
</job_posting>

<current_resume>
{resume}
</current_resume>{notes}"""
    return _complete(_TAILOR_SYSTEM, prompt, key, max_tokens=24000)


_LETTER_SYSTEM = """You write cover letters that hiring managers actually finish reading.

Hard rules:
- Every claim must come from the resume. Never invent experience, metrics, or enthusiasm \
about specifics the candidate has no stated connection to.
- Three tight paragraphs, under 300 words total. No filler openers ("I am writing to \
apply for..."), no restating the whole resume.
- Paragraph 1: the single strongest reason this candidate fits this specific role. \
Paragraph 2: concrete evidence from their actual work. Paragraph 3: brief close.
- Plain, direct language. No buzzword stacking, no "passionate about synergy".

Output the letter body in markdown, starting with the greeting. No commentary."""


def cover_letter(resume: str, job: dict, key: str, extra_notes: str = "") -> str:
    notes = f"\n\nAdditional instructions from the candidate:\n{extra_notes}" if extra_notes.strip() else ""
    prompt = f"""Write a cover letter for this job.

<job_posting>
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}

{job.get('description', '')}
</job_posting>

<resume>
{resume}
</resume>{notes}"""
    return _complete(_LETTER_SYSTEM, prompt, key, max_tokens=8000)
