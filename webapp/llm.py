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


def show_error(exc: Exception) -> None:
    """Render a generation failure: plain message up top, raw detail on demand."""
    import streamlit as st

    st.error(str(exc))
    detail = getattr(exc, "detail", "")
    if detail and detail != str(exc):
        with st.expander("Technical details"):
            st.code(detail)


def _complete(system: str, prompt: str, max_tokens: int = 20000) -> str:
    cfg = settings()
    return providers.complete(
        cfg["provider"], system, prompt, cfg["key"], cfg["model"],
        max_tokens=max_tokens, base_url=cfg["base_url"],
    )


# Resume tailoring is an editing job, not a writing job. Left unconstrained,
# models rewrite every line — which erases the candidate's voice, makes the
# change-diff useless to review, and multiplies the chance of a subtly invented
# claim. So the prompt states a change budget and demands untouched lines come
# back byte-identical.
_TAILOR_BASE = """You are an expert resume editor making TARGETED EDITS to an existing \
resume. You are not rewriting it.

The candidate wrote this resume. It is already theirs, in their voice, and most of it \
is fine. Your job is to make the smallest set of changes that make it land for one \
specific posting.

Absolute rules:
- NEVER invent employers, titles, dates, degrees, certifications, tools, or metrics. \
Every fact must be traceable to the original resume.
- Lines you are not deliberately changing must be reproduced EXACTLY, character for \
character. Do not "improve" wording, punctuation, or formatting on a line you had no \
specific reason to touch.
- Never delete a whole role, employer, or date range.
- Keep it ATS-friendly: plain markdown, standard headings, no tables or columns.

Prefer, in this order:
1. Reordering — put the most relevant bullets and skills first.
2. The headline/summary — this is where targeting a posting pays off most.
3. Terminology — where the resume already describes the same work, use the posting's \
word for it (e.g. "LLM output validation" -> "model evaluation" if that's their term).
4. Only then, rewording a specific bullet that buries relevant experience.

Do NOT paraphrase bullets that are already clear and relevant. A resume where every \
line changed is a failure, not a thorough job.

{budget}

Output the complete resume in markdown and nothing else — no preamble, no commentary, \
no notes about what you changed."""

_BUDGETS = {
    "Light": (
        "CHANGE BUDGET: edit at most about 15% of the lines. Typically that is the "
        "headline, the summary, and a handful of bullets. Everything else comes back "
        "untouched and identical."
    ),
    "Balanced": (
        "CHANGE BUDGET: edit at most about 30% of the lines. Reorder freely, rewrite "
        "the summary, and revise the bullets that matter most for this posting. Leave "
        "the remaining majority identical."
    ),
    "Thorough": (
        "CHANGE BUDGET: edit at most about 60% of the lines. You may restructure "
        "sections and rewrite bullets to match the posting, but still leave anything "
        "already relevant and well-phrased exactly as written."
    ),
}

STRENGTHS = list(_BUDGETS)
DEFAULT_STRENGTH = "Light"


def tailor_resume(
    resume: str, job: dict, extra_notes: str = "", strength: str = DEFAULT_STRENGTH
) -> str:
    system = _TAILOR_BASE.format(budget=_BUDGETS.get(strength, _BUDGETS[DEFAULT_STRENGTH]))
    notes = f"\n\nAdditional instructions from the candidate:\n{extra_notes}" if extra_notes.strip() else ""
    prompt = f"""Make targeted edits to this resume for the job posting below.

<job_posting>
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}

{job.get('description', '')}
</job_posting>

<current_resume>
{resume}
</current_resume>{notes}"""
    return _complete(system, prompt, max_tokens=24000)


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
