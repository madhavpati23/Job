"""Derive search terms from a resume, so the user needn't supply any.

The app already ranks results against the resume; this closes the loop by
choosing what to *fetch* from it too — job titles to search for and cities to
search in. Deterministic and offline: no API key, no model call, so it works
for every visitor.
"""

from __future__ import annotations

import re
from collections import Counter

# Nouns that make a phrase a job title. A line containing one of these, short
# enough to be a heading, is almost always a role — not prose.
_ROLE_NOUNS = {
    "engineer", "engineering", "developer", "manager", "director", "lead",
    "architect", "analyst", "scientist", "specialist", "consultant",
    "administrator", "designer", "researcher", "strategist", "coordinator",
    "sdet", "qa", "tester", "programmer", "devops", "sre", "recruiter",
    "accountant", "nurse", "teacher", "attorney", "technician", "supervisor",
    "officer", "associate", "president", "head", "chief", "principal", "staff",
}

# Words that appear beside a title but aren't part of one.
_TITLE_NOISE = {
    "resume", "curriculum", "vitae", "cv", "summary", "objective", "profile",
    "experience", "employment", "history", "education", "skills", "projects",
    "certifications", "references", "contact", "present", "current",
}

# Stripped so a search isn't pinned to one rung. Deliberately excludes manager,
# director, lead, head, and chief — those are the role, not a modifier.
_SENIORITY = ("principal", "staff", "senior", "sr", "sr.", "junior", "jr", "jr.",
              "associate", "vp", "vice", "ii", "iii", "iv")

# Fragments naming an employer rather than a role.
_COMPANY_HINTS = {
    "technologies", "technology", "inc", "inc.", "llc", "ltd", "corp", "corp.",
    "corporation", "solutions", "systems", "labs", "group", "consulting",
    "services", "software", "global", "usa", "india", "gmbh", "limited",
    "partners", "holdings", "enterprises", "agency", "studios", "university",
    "college", "hospital", "clinic", "institute", "bank", "insurance",
}

# "Austin, TX" / "San Francisco, CA" — the shape US resumes use for locations.
_CITY_STATE = re.compile(r"\b([A-Z][a-zA-Z.]+(?:[ -][A-Z][a-zA-Z.]+){0,2}),\s*([A-Z]{2})\b")
_REMOTE = re.compile(r"\b(remote|work from home|wfh|distributed)\b", re.I)

# US state codes, so "Dear, HR" or "Java, JS" don't parse as a place.
_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}

# Resume rows pack "Company, Title (Client: X) - Dates" onto one line, so split
# on every separator that can divide those fields — commas included.
_LINE_SPLIT = re.compile(r"[|•·,;\t]|\s{3,}| - | – | — ")
_PARENS = re.compile(r"\([^)]*\)")
_DATES = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b.*|"
    r"\b(19|20)\d{2}\b.*|\bpresent\b.*", re.I,
)
_CLEAN = re.compile(r"^[^A-Za-z]+|[^A-Za-z0-9+#/)]+$")


def _candidate_titles(resume: str) -> list[str]:
    """Title-shaped fragments, most frequent first.

    Lines near the top score double: a resume's headline states the role the
    person wants, which beats any single past job title.
    """
    found: list[str] = []
    lines = [l for l in (resume or "").splitlines()]
    for idx, raw_line in enumerate(lines):
        line = _DATES.sub("", _PARENS.sub(" ", raw_line))
        for part in _LINE_SPLIT.split(line):
            phrase = _CLEAN.sub("", part.strip().strip("#*-–—•").strip())
            if not (3 <= len(phrase) <= 50):
                continue
            words = phrase.split()
            if not (1 < len(words) <= 5):
                continue
            lowered = [w.lower().strip(",.") for w in words]
            if not any(w in _ROLE_NOUNS for w in lowered):
                continue
            if any(w in _TITLE_NOISE or w in _COMPANY_HINTS for w in lowered):
                continue
            # Dates, bullet prose, and sentences aren't titles.
            if any(c.isdigit() for c in phrase) or phrase.endswith((".", ":")):
                continue
            # Titles are capitalized; a fragment sliced out of a sentence
            # ("prepared and implemented QA roadmap") is not.
            if not phrase[0].isupper():
                continue
            capitalized = sum(1 for w in words if w[0].isupper())
            if capitalized * 2 < len(words):
                continue
            found.append(" ".join(words))
            if idx < 6:  # headline region
                found.append(" ".join(words))
    return [t for t, _ in Counter(found).most_common()]


def _generalize(title: str) -> str:
    """Drop seniority so the search matches more than one exact rung."""
    words = [w for w in title.split() if w.lower().strip(",.") not in _SENIORITY]
    return " ".join(words).strip() or title


def derive_titles(resume: str, limit: int = 4) -> list[str]:
    """Search-ready role titles, de-duplicated and seniority-stripped."""
    out: list[str] = []
    seen: set[str] = set()
    for title in _candidate_titles(resume):
        general = _generalize(title)
        key = general.lower()
        if len(key) < 4 or key in seen:
            continue
        # Skip a title that's just a longer form of one we already have.
        if any(key in s or s in key for s in seen):
            continue
        seen.add(key)
        out.append(general)
        if len(out) >= limit:
            break
    return out


# Words that make "<X>, ST" an employer rather than a city — "Ascension Health,
# MI" and "LPL Financial, NC" are companies with a state after them, and reading
# them as places sends the search to cities that don't exist.
_NOT_A_CITY = _COMPANY_HINTS | {
    "health", "healthcare", "financial", "finance", "capital", "bank", "media",
    "motors", "foods", "energy", "pharma", "pharmaceuticals", "medical",
    "logistics", "airlines", "communications", "networks", "digital", "data",
    "analytics", "ventures", "brands", "industries", "manufacturing", "retail",
    "management", "associates", "group", "center", "centre", "solutions",
    "international", "national", "american", "general", "federal", "state",
}


def _looks_like_city(name: str) -> bool:
    words = [w.lower().strip(".") for w in name.split()]
    if any(w in _NOT_A_CITY for w in words):
        return False
    return not any(w in _ROLE_NOUNS or w in _TITLE_NOISE for w in words)


def derive_locations(resume: str, limit: int = 3) -> list[str]:
    """Where the candidate is, plus Remote when the resume mentions remote work.

    The header is trusted first: a resume's own address sits in the first few
    lines, whereas later "City, ST" matches are employer locations — or
    employers themselves, when a company name precedes a state code.
    """
    lines = [l for l in (resume or "").splitlines() if l.strip()]
    header = "\n".join(lines[:4])

    def _found(text: str) -> list[str]:
        out = []
        for city, state in _CITY_STATE.findall(text or ""):
            if state in _STATES and _looks_like_city(city):
                out.append(f"{city}, {state}")
        return out

    locations = list(dict.fromkeys(_found(header)))[:limit]
    if not locations:
        # No address up top — fall back to the most frequently named place.
        counts = Counter(_found(resume))
        locations = [c for c, _ in counts.most_common(limit)]

    if _REMOTE.search(resume or ""):
        locations.append("Flexible / Remote")
    return locations


def derive_search(resume: str) -> dict:
    """Everything the search form needs, inferred from the resume."""
    titles = derive_titles(resume)
    return {
        "keywords": titles,
        "locations": derive_locations(resume),
    }
