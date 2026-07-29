"""Pull the terms that actually matter out of a job posting.

Naive frequency counting fails badly on real postings: a company's about-us
preamble is far more repetitive than its requirements list, so brand names and
marketing copy outrank the skills the role is screening for. A WebMD posting for
"Senior Manager, Test Automation & AI Evaluation" scored `medscape`, `krames`,
`journey`, and `wellness` above every technical term in the requirements.

So this module does three things frequency alone can't:
  * weights the requirements section far above the preamble,
  * drops corporate filler and the hiring company's own name/brands,
  * matches singular/plural so `platform` in a resume covers `platforms`.
"""

from __future__ import annotations

import re
from collections import Counter

# Keep +/#/. inside a token so "c++", "c#", "node.js", and "ci/cd" survive, then
# strip trailing punctuation so "platforms." and "platforms" aren't two terms.
_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+#./-]*")
_TRIM = ".,;:/-"

_GENERIC = {
    "the", "and", "for", "with", "you", "our", "are", "will", "this", "that",
    "have", "your", "from", "but", "not", "all", "can", "has", "who", "job",
    "work", "team", "role", "company", "experience", "years", "requirements",
    "including", "across", "their", "they", "what", "how", "about", "were",
    "was", "its", "his", "her", "them", "then", "than", "into", "out", "any",
    "may", "each", "such", "also", "more", "most", "other", "some", "been",
    "which", "when", "where", "while", "would", "could", "should", "must",
}

# Corporate boilerplate: frequent in postings, meaningless as a skill signal.
_CORPORATE = {
    "growth", "journey", "mission", "vision", "values", "partner", "partners",
    "people", "better", "best", "leading", "leader", "industry", "division",
    "brands", "brand", "organization", "organizations", "enterprise", "global",
    "world", "worlds", "customer", "customers", "client", "clients", "business",
    "solutions", "solution", "platform", "platforms", "products", "product",
    "services", "service", "innovative", "innovation", "passionate", "dynamic",
    "exciting", "opportunity", "opportunities", "join", "joining", "career",
    "careers", "benefits", "salary", "compensation", "equal", "diversity",
    "inclusive", "inclusion", "employer", "candidates", "candidate", "applicants",
    "position", "positions", "hiring", "apply", "resume", "million", "billion",
    "founded", "headquarters", "committed", "commitment", "focused", "focus",
    "powered", "driven", "help", "helping", "make", "making", "support",
    "supporting", "ensure", "ensuring", "provide", "providing", "including",
    "strong", "excellent", "ability", "able", "well", "new", "great", "high",
    "stages", "discovery", "recovery", "wellness", "combination", "guide",
    # Section headers — structural, not skills.
    "responsibilities", "duties", "overview", "summary", "description",
    "preferred", "required", "basic", "minimum", "plus", "bonus", "nice",
    "qualifications", "requirement", "include", "includes", "included",
    # Generic action verbs: every posting has them, they discriminate nothing.
    "perform", "performing", "conduct", "conducting", "maintain", "maintaining",
    "build", "building", "drive", "driving", "manage", "managing", "lead",
    "develop", "developing", "create", "creating", "deliver",
    "delivering", "collaborate", "collaborating", "own", "owning",
    "define", "defining", "implement", "implementing", "hands", "using", "use",
}

_STOP = _GENERIC | _CORPORATE

# Where the boilerplate ends and the actual asks begin. Terms after the first
# match are weighted up — that's the part describing the job.
_REQ_MARKER = re.compile(
    r"(what you[''’]?ll (do|bring)|what we[''’]?re looking for|"
    r"requirements|qualifications|responsibilities|your role|the role|"
    r"must[- ]have|nice[- ]to[- ]have|skills|you (will|should) have|"
    r"we[''’]?d love|about you|key duties)",
    re.I,
)
_REQ_WEIGHT = 4


def _tokens(text: str) -> list[str]:
    out = []
    for raw in _WORD.findall(text or ""):
        tok = raw.lower().strip(_TRIM)
        if len(tok) > 2 and tok not in _STOP and not tok.isdigit():
            out.append(tok)
    return out


def _variants(token: str) -> set[str]:
    """Inflections of a term, so a resume saying "testing" covers "test".

    Deliberately shallow — a real stemmer would conflate unrelated words and
    report coverage the candidate can't defend in an interview.
    """
    forms = {token}
    if token.endswith("ies") and len(token) > 4:
        forms.add(token[:-3] + "y")
    elif token.endswith("es") and len(token) > 4:
        forms.add(token[:-2])
    if token.endswith("s") and len(token) > 3:
        forms.add(token[:-1])
    else:
        forms.add(token + "s")

    # Verb/gerund drift: test <-> testing <-> tested.
    for stem in list(forms):
        if stem.endswith("ing") and len(stem) > 5:
            forms.add(stem[:-3])
        elif stem.endswith("ed") and len(stem) > 4:
            forms.add(stem[:-2])
        elif len(stem) > 3 and not stem.endswith("s"):
            forms.update({stem + "ing", stem + "ed"})
    return forms


def _company_tokens(company: str) -> set[str]:
    """The employer's own name — never a transferable skill."""
    return set(_tokens(company)) if company else set()


def extract(description: str, company: str = "", n: int = 25) -> list[str]:
    """Return the `n` most job-relevant terms from a posting."""
    text = description or ""
    match = _REQ_MARKER.search(text)
    if match:
        preamble, requirements = text[: match.start()], text[match.start() :]
    else:
        preamble, requirements = "", text

    counts: Counter[str] = Counter(_tokens(preamble))
    for tok in _tokens(requirements):
        counts[tok] += _REQ_WEIGHT

    for tok in _company_tokens(company):
        counts.pop(tok, None)

    return [w for w, _ in counts.most_common(n)]


def covered(token: str, resume: str) -> bool:
    """Is this term present in the resume, allowing singular/plural drift?"""
    low = (resume or "").lower()
    return any(re.search(rf"(?<!\w){re.escape(v)}(?!\w)", low) for v in _variants(token))


def gap_analysis(resume: str, description: str, company: str = "", n: int = 25) -> dict:
    """Split a posting's key terms into those the resume covers and those it misses."""
    terms = extract(description, company, n)
    hits = [t for t in terms if covered(t, resume)]
    return {"covered": hits, "missing": [t for t in terms if t not in hits]}
