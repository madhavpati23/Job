"""Local, deterministic job<->resume scoring. No LLM, no network."""

from __future__ import annotations

import math
import re
from collections import Counter

from .sources import Job

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.]{1,}")
_STOP = {
    "the", "and", "for", "with", "you", "our", "are", "will", "this", "that",
    "have", "your", "from", "but", "not", "all", "can", "has", "who", "job",
    "work", "team", "role", "company", "experience", "years", "requirements",
}


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP and len(w) > 2]


def _vector(text: str) -> Counter:
    return Counter(_tokens(text))


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# Role terms that, when present in the *title*, indicate a genuine QA/test/eval
# fit for this user's profile. A title match adds a strong bonus so real roles
# outrank jobs that merely mention "test" somewhere in the description.
_ROLE_TERMS = (
    "qa", "quality", "sdet", "test", "tester", "testing",
    "evaluation", "eval", "validation", "automation",
)


def _title_role_bonus(title: str) -> tuple[float, list[str]]:
    tl = f" {title.lower()} "
    hits = [t for t in _ROLE_TERMS if f" {t} " in tl or f" {t}," in tl or f"/{t}" in tl]
    if not hits:
        return 0.0, []
    # base 18 for any role-title match, +4 per extra distinct term, capped.
    return min(30.0, 18.0 + 4.0 * (len(hits) - 1)), hits


# Titles below this user's level (15-yr lead). A match applies a heavy penalty
# so junior/admin roles stop floating to the top on keyword overlap alone.
_JUNIOR_TERMS = (
    "assistant", "intern", "internship", "junior", "jr", "coordinator",
    "entry", "entry-level", "associate", "trainee", "apprentice", "graduate",
    "clerk", "fellow",
)


def _seniority_penalty(title: str) -> tuple[float, list[str]]:
    tl = f" {title.lower()} "
    hits = [t for t in _JUNIOR_TERMS if f" {t} " in tl or f" {t}," in tl or f"/{t}" in tl]
    return (25.0 if hits else 0.0), hits


# Phrases that, in a *title*, signal a genuine AI-testing / LLM-eval role — the
# user's actual target. Stronger bonus than generic QA terms so these top the list.
_AI_TEST_PHRASES = (
    "red team", "red teamer", "redteam", "evals", "evaluation", "benchmark",
    "model quality", "model behavior", "llm", "safeguards", "hallucination",
    "trust and safety", "ai quality", "ai test", "model testing", "alignment",
)


def _ai_test_bonus(title: str) -> tuple[float, list[str]]:
    tl = title.lower()
    hits = [p for p in _AI_TEST_PHRASES if p in tl]
    if not hits:
        return 0.0, []
    return min(40.0, 28.0 + 4.0 * (len(hits) - 1)), hits


# Visa-sponsorship signals in a posting. We can only act on explicit statements;
# silence means unknown (most US postings don't say). "no-sponsor" is the most
# useful signal — it lets us drop roles the user is ineligible for.
_NO_SPONSOR = re.compile(
    r"(no|not|unable to|cannot|won'?t|do(es)? not (provide|offer)).{0,20}"
    r"(visa )?sponsor|without sponsor|sponsorship is not",
    re.I,
)
_YES_SPONSOR = re.compile(
    r"we (do |will |)sponsor|sponsor visas|visa sponsorship( is)? (available|offered|provided)",
    re.I,
)


# Salary figures in description text, e.g. "$230,000" or "$230,000 — $270,000".
_SALARY = re.compile(r"\$\s?(\d{2,3}(?:,\d{3})|\d{3}(?:\.\d)?\s?[kK])")


def _extract_salary(text: str) -> float:
    """Largest plausible annual USD salary found in text (0 if none)."""
    best = 0.0
    for raw in _SALARY.findall(text or ""):
        s = raw.replace(",", "").lower().strip()
        val = float(s[:-1]) * 1000 if s.endswith("k") else float(s)
        if 30_000 <= val <= 1_000_000:
            best = max(best, val)
    return best


def effective_salary(job: Job) -> float:
    """Best salary signal: structured (Adzuna) first, else parsed from text."""
    structured = max(getattr(job, "salary_max", 0) or 0, getattr(job, "salary_min", 0) or 0)
    return structured if structured else _extract_salary(job.description)


def _visa_signal(description: str) -> str:
    d = description or ""
    if _NO_SPONSOR.search(d):
        return "no-sponsor"
    if _YES_SPONSOR.search(d):
        return "sponsors"
    return "unknown"


# Countries and regions that mark a posting as non-US. Matched on word
# boundaries: a plain substring test drops "New Mexico" for "Mexico" and every
# Atlanta job for "Georgia". "Georgia" and "Jordan" are omitted entirely —
# they collide with a US state and a common name, and the cost of a false
# exclusion (losing a real job) is worse than an occasional foreign result.
_NON_US = (
    "india", "united kingdom", "england", "scotland", "wales", "ireland",
    "dublin", "london", "france", "germany", "spain", "portugal", "italy",
    "netherlands", "belgium", "poland", "romania", "czech", "austria",
    "switzerland", "sweden", "norway", "denmark", "finland", "greece",
    "hungary", "bulgaria", "croatia", "serbia", "ukraine", "turkey",
    "canada", "ontario", "quebec", "toronto", "vancouver", "montreal",
    "australia", "sydney", "melbourne", "new zealand", "japan", "tokyo",
    "china", "shanghai", "beijing", "singapore", "malaysia", "indonesia",
    "philippines", "vietnam", "thailand", "korea", "hong kong", "taiwan",
    "brazil", "brasil", "argentina", "chile", "colombia", "peru",
    "mexico",  # the (?<!new ) guard keeps New Mexico
    "south africa", "nigeria", "kenya", "egypt", "israel", "uae",
    "dubai", "saudi", "qatar", "pakistan", "bangladesh", "sri lanka",
    "emea", "apac", "latam", "europe", "asia", "africa",
)
_NON_US_RE = re.compile(
    r"(?<!new )\b(" + "|".join(re.escape(c) for c in _NON_US) + r")\b", re.I
)

_US_SIGNALS = re.compile(
    r"\b(usa|u\.s\.a?|united states|us[- ]based|remote[- ]us|"
    r"al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|"
    r"ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|"
    r"wa|wv|wi|wy|dc)\b",
    re.I,
)


def is_us_location(location: str) -> bool:
    """Keep US and unknown/remote locations; drop clearly foreign ones.

    Unknown is treated as keep — many postings omit a location entirely, and
    silently hiding them would be worse than showing a few foreign results.
    """
    loc = (location or "").strip()
    if not loc:
        return True
    if _NON_US_RE.search(loc):
        # "Remote - US or Canada" is still open to a US applicant.
        return bool(_US_SIGNALS.search(loc))
    return True


def score_job(resume: str, job: Job, must_have: list[str] | None = None) -> dict:
    """Return a fit score (0-100) plus the keywords driving it."""
    rvec = _vector(resume)
    jtext = f"{job.title} {job.title} {job.description}"  # weight title
    jvec = _vector(jtext)

    sim = _cosine(rvec, jvec)
    overlap = sorted(set(rvec) & set(jvec), key=lambda t: -(rvec[t] + jvec[t]))[:12]

    must_have = must_have or []
    jl = jtext.lower()
    missing = [kw for kw in must_have if kw.lower() not in jl]

    bonus, role_hits = _title_role_bonus(job.title)
    ai_bonus, ai_hits = _ai_test_bonus(job.title)
    score = sim * 100 + bonus + ai_bonus

    # Penalize junior/admin titles below this user's level.
    jr_penalty, jr_hits = _seniority_penalty(job.title)
    score -= jr_penalty

    # Penalize thin postings (e.g. LinkedIn stubs): too few words to trust the
    # match, and a single overlapping keyword shouldn't dominate the score.
    desc_words = len(_WORD.findall(job.description or ""))
    thin = desc_words < 40
    if thin:
        score -= 15.0

    if must_have:
        penalty = (len(missing) / len(must_have)) * 30
        score -= penalty

    # Visa: confirmed sponsors get a small boost; explicit non-sponsors sink hard.
    visa = _visa_signal(job.description)
    if visa == "sponsors":
        score += 8.0
    elif visa == "no-sponsor":
        score -= 40.0

    score = max(0.0, round(score, 1))

    flags = []
    if ai_hits:
        flags.append(f"ai-testing:{','.join(ai_hits)}")
    if jr_hits:
        flags.append(f"junior-title:{','.join(jr_hits)}")
    if thin:
        flags.append(f"thin-desc:{desc_words}w")
    if visa != "unknown":
        flags.append(f"visa:{visa}")

    return {
        "score": score,
        "matched_keywords": overlap,
        "title_role_match": role_hits,
        "ai_testing_match": ai_hits,
        "visa": visa,
        "salary": effective_salary(job),
        "penalty_flags": flags,
        "missing_must_have": missing,
    }


def rank_jobs(
    resume: str,
    jobs: list[Job],
    query: str | None = None,
    must_have: list[str] | None = None,
    exclude: list[str] | None = None,
    location: str | None = None,
    exclude_locations: list[str] | None = None,
    min_salary: float | None = None,
    us_only: bool = False,
    limit: int = 10,
) -> list[dict]:
    """Filter by query/exclude/location, score against resume, return top `limit`.

    Args:
        query: keyword that must appear in title or description.
        must_have: skills that lower the score if missing.
        exclude: if any of these appear in the title, the job is dropped
            (e.g. "manufacturing", "hardware" to kill non-software test roles).
        location: substring the job location must contain, OR "remote" to keep
            anything marked remote/anywhere. Case-insensitive.
        exclude_locations: drop a job if its location contains any of these
            (e.g. country names to keep the search US-focused). A job is kept
            despite a match if it's also marked remote/worldwide.
    """
    if query:
        q = query.lower()
        jobs = [j for j in jobs if q in j.title.lower() or q in j.description.lower()]

    if exclude:
        ex = [e.lower() for e in exclude]
        jobs = [j for j in jobs if not any(e in j.title.lower() for e in ex)]

    if us_only:
        jobs = [j for j in jobs if is_us_location(j.location)]

    if exclude_locations:
        xl = [e.lower() for e in exclude_locations]
        jobs = [j for j in jobs if not any(e in j.location.lower() for e in xl)]

    if location:
        loc = location.lower()
        def _loc_ok(j: Job) -> bool:
            jl = j.location.lower()
            if loc in ("remote", "anywhere"):
                return "remote" in jl or "anywhere" in jl or jl == "" or "worldwide" in jl
            return loc in jl or "remote" in jl or "anywhere" in jl
        jobs = [j for j in jobs if _loc_ok(j)]

    scored = []
    for j in jobs:
        s = score_job(resume, j, must_have) if resume else {"score": 0.0, "salary": effective_salary(j)}
        # Keep roles whose salary is unknown (0) OR meets the floor; drop only
        # those with a KNOWN salary below it.
        if min_salary and 0 < s.get("salary", 0) < min_salary:
            continue
        scored.append({**j.to_dict(), **s, "description": j.description[:400]})

    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored[:limit]
