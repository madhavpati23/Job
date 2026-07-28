"""Claude-backed resume tailoring and cover-letter writing.

The app works without an API key — `jobapply_mcp.drafting` still produces a
grounded scaffold, and the gap analysis below is pure Python. A key upgrades
both from "structured starting point" to "finished draft".
"""

from __future__ import annotations

from jobapply_mcp import keywords as kw
from webapp import providers
from webapp.providers import ProviderError  # re-exported for callers


def keywords(text: str, company: str = "", n: int = 25) -> list[str]:
    """The terms a posting is actually screening for. See jobapply_mcp.keywords."""
    return kw.extract(text, company, n)


def gap_analysis(
    resume: str, job_description: str, company: str = "", n: int = 25
) -> dict[str, list[str]]:
    """Which posting keywords the resume already covers, and which it misses."""
    return kw.gap_analysis(resume, job_description, company, n)


# --- LLM backends ---------------------------------------------------------
# Provider selection lives in webapp/providers.py; these are thin helpers the
# views call so no view has to know which backend is active.


def settings() -> dict:
    """The active provider/model/key/base_url, read from session state."""
    import streamlit as st

    pid = st.session_state.get("llm_provider", providers.DEFAULT_PROVIDER)
    provider = providers.get(pid)
    return {
        "provider": provider,
        "key": providers.resolve_key(provider, st.session_state.get("llm_key", "")),
        "model": st.session_state.get("llm_model", "") or provider.default_model,
        "base_url": st.session_state.get("llm_base_url", ""),
    }


def available() -> bool:
    """Can we actually generate right now?"""
    cfg = settings()
    if not providers.installed(cfg["provider"]):
        return False
    # A local OpenAI-compatible server (Ollama, LM Studio) needs no key.
    return bool(cfg["key"] or cfg["base_url"])


def _complete(system: str, prompt: str, max_tokens: int = 20000) -> str:
    cfg = settings()
    return providers.complete(
        cfg["provider"], system, prompt, cfg["key"], cfg["model"],
        max_tokens=max_tokens, base_url=cfg["base_url"],
    )


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


def tailor_resume(resume: str, job: dict, extra_notes: str = "") -> str:
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
    return _complete(_TAILOR_SYSTEM, prompt, max_tokens=24000)


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


def cover_letter(resume: str, job: dict, extra_notes: str = "") -> str:
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
    return _complete(_LETTER_SYSTEM, prompt, max_tokens=8000)
