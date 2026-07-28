"""Build a cover-letter scaffold from a resume + a job posting.

Deterministic: no LLM call here. It assembles a structured starter draft with
the relevant facts in place; Claude (the host) refines the prose. This keeps the
draft grounded in the real posting and the user's real experience.
"""

from __future__ import annotations

import re
from collections import Counter

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.]{1,}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_STOP = {
    "the", "and", "for", "with", "you", "our", "are", "will", "this", "that",
    "have", "your", "from", "but", "not", "all", "can", "has", "who", "job",
    "work", "team", "role", "company", "experience", "years", "requirements",
    "including", "across", "their", "they", "what", "how", "about",
}


def _keywords(text: str, n: int = 15) -> list[str]:
    toks = [w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP and len(w) > 2]
    return [w for w, _ in Counter(toks).most_common(n)]


def _contact(resume: str) -> tuple[str, str]:
    """Best-effort name and contact line pulled from the top of a resume."""
    lines = [l.strip().lstrip("# ").strip() for l in (resume or "").split("\n")]
    lines = [l for l in lines if l]
    name = ""
    for line in lines[:5]:
        # A name line is short, has no digits, and isn't an email/URL.
        if 2 <= len(line.split()) <= 5 and not any(c.isdigit() for c in line) and "@" not in line:
            name = line
            break
    contact = " | ".join(
        m.group(0) for m in (_EMAIL.search(resume or ""), _PHONE.search(resume or "")) if m
    )
    return name or "[Your name]", contact or "[Your email | phone]"


def build_scaffold(resume: str, job: dict) -> str:
    """Return a markdown cover-letter scaffold tailored to this posting."""
    company = job.get("company", "the company")
    title = job.get("title", "the role")
    desc = job.get("description", "")
    name, contact = _contact(resume)

    job_kw = _keywords(desc, 15)
    resume_l = resume.lower()
    overlap = [k for k in job_kw if k in resume_l]
    gaps = [k for k in job_kw if k not in resume_l]

    overlap_line = ", ".join(overlap[:8]) or "(none auto-detected — add manually)"
    gap_line = ", ".join(gaps[:8]) or "(none)"

    return f"""## Cover letter — {title} at {company}

> Rewrite the body below into a tight 3-paragraph letter. Lead with the single
> strongest reason you fit *this* posting, then concrete evidence from your actual
> work, then a brief close. Keep every claim grounded in the resume.

**Posting keywords that match the resume:** {overlap_line}
**Posting keywords NOT obviously in the resume (address or omit):** {gap_line}

---

Dear Hiring Team at {company},

I'm applying for the **{title}** role. [One sentence on the strongest reason you
fit this specific posting — draw on the matching keywords above.]

[Two or three sentences of concrete evidence from your résumé: what you built or
led, at what scale, with what result. Tie it back to: {overlap_line}.]

I'd welcome the chance to bring this background to {company}. Thank you for your
consideration.

Sincerely,
{name}
{contact}
"""
