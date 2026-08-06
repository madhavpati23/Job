"""Job fetching + ranking for the web app.

Wraps the existing `jobapply_mcp` source and scoring modules. Those are pure
functions over data, so they're reused unchanged; only the config assembly and
caching layer is web-specific.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from jobapply_mcp.matching import rank_jobs
from jobapply_mcp.sources import Job, fetch_all
from jobapply_mcp.storage import load_config

# Board tokens the user can toggle on. Kept here rather than in config.json so the
# deployed app has sensible defaults even with no config file present.
SOURCE_LABELS = {
    "greenhouse": "Greenhouse boards",
    "lever": "Lever boards",
    "ashby": "Ashby boards",
    "remoteok": "RemoteOK",
    "remotive": "Remotive",
    "muse": "The Muse (by city)",
    "smartrecruiters": "SmartRecruiters",
    "workday": "Workday (large US employers)",
    "jobicy": "Jobicy (remote)",
    "himalayas": "Himalayas (remote)",
    "arbeitnow": "Arbeitnow (mostly EU)",
    "usajobs": "USAJOBS (US federal)",
    "adzuna": "Adzuna (nationwide US)",
}

# Sensible for a US-focused search out of the box. Arbeitnow is mostly German
# and USAJOBS needs a key, so neither is on by default.
DEFAULT_SOURCES = [
    "greenhouse", "lever", "ashby", "remotive", "muse", "jobicy", "himalayas", "adzuna",
]


# Offered in the location picker. The Muse matches on exact strings like these,
# so they're spelled the way its API expects. Users can also type their own.
LOCATION_OPTIONS = [
    "Flexible / Remote",
    "Atlanta, GA", "Austin, TX", "Boston, MA", "Charlotte, NC", "Chicago, IL",
    "Dallas, TX", "Denver, CO", "Detroit, MI", "Houston, TX", "Las Vegas, NV",
    "Los Angeles, CA", "Miami, FL", "Minneapolis, MN", "Nashville, TN",
    "New York, NY", "Philadelphia, PA", "Phoenix, AZ", "Pittsburgh, PA",
    "Portland, OR", "Raleigh, NC", "Salt Lake City, UT", "San Antonio, TX",
    "San Diego, CA", "San Francisco, CA", "San Jose, CA", "Seattle, WA",
    "St. Louis, MO", "Tampa, FL", "Washington, DC",
]


def load_base_config() -> dict[str, Any]:
    """Board lists and search terms, preferring a private config.local.json."""
    return load_config()


def adzuna_credentials() -> tuple[str, str]:
    """Resolve Adzuna keys: env, then Streamlit secrets, then local config.

    The last fallback keeps the local web app and the CLI on one set of keys —
    the CLI reads them straight out of the config file. It can only ever pick up
    a gitignored config.local.json, since the committed config.json ships empty.
    """
    app_id, app_key = os.environ.get("ADZUNA_APP_ID", ""), os.environ.get("ADZUNA_APP_KEY", "")
    if app_id and app_key:
        return app_id, app_key

    try:
        import streamlit as st

        app_id = str(st.secrets.get("ADZUNA_APP_ID", "")) or app_id
        app_key = str(st.secrets.get("ADZUNA_APP_KEY", "")) or app_key
    except Exception:
        pass
    if app_id and app_key:
        return app_id, app_key

    local = load_config().get("adzuna") or {}
    return str(local.get("app_id", "")), str(local.get("app_key", ""))


def usajobs_credentials() -> tuple[str, str]:
    """USAJOBS wants the email registered with the key, plus the key itself."""
    email = os.environ.get("USAJOBS_EMAIL", "")
    api_key = os.environ.get("USAJOBS_API_KEY", "")
    if email and api_key:
        return email, api_key
    try:
        import streamlit as st

        return str(st.secrets.get("USAJOBS_EMAIL", "")), str(st.secrets.get("USAJOBS_API_KEY", ""))
    except Exception:
        return "", ""


def company_slugs(names: list[str]) -> list[str]:
    """Candidate ATS board tokens for company names the user typed.

    A board token is the company slug in its careers URL, and companies are
    inconsistent about it — "Acme Corp" may be `acmecorp`, `acme-corp`, or
    `acme`. Every variant is tried; the fetchers return [] for tokens that don't
    exist, so guessing wide costs one cheap 404 rather than an error.
    """
    out: list[str] = []
    for raw in names:
        name = re.sub(r"[^a-z0-9 -]", "", (raw or "").strip().lower())
        if not name:
            continue
        words = name.split()
        for candidate in ("".join(words), "-".join(words), words[0]):
            if candidate and candidate not in out:
                out.append(candidate)
    return out


def build_config(
    enabled: list[str],
    keywords: list[str],
    locations: list[str],
    companies: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble a `fetch_all` config from the user's UI selections.

    Empty keywords/locations mean "no filter" and are passed through as such —
    they are never backfilled from config, since a blank field is a choice the
    user made and silently substituting our values would misreport the search.
    """
    base = load_base_config()
    cfg: dict[str, Any] = {}

    # Companies the user named are tried on every ATS: we don't know which one
    # a given employer uses, and an unknown token simply returns nothing.
    extra = company_slugs(companies or [])
    for name in ("greenhouse", "lever", "ashby"):
        if name in enabled:
            cfg[name] = list(dict.fromkeys(list(base.get(name, [])) + extra))
    if "smartrecruiters" in enabled:
        cfg["smartrecruiters"] = base.get("smartrecruiters", [])
    if "remoteok" in enabled:
        cfg["remoteok"] = True
    if "remotive" in enabled:
        cfg["remotive"] = True
        cfg["remotive_searches"] = keywords or [""]
    if "muse" in enabled:
        cfg["muse"] = True
        # The Muse searches one city per request and has no nationwide query, so
        # "no location chosen" means sweeping every metro we know. That is the
        # only keyless source giving real US-wide breadth — a single empty-string
        # query returns one page and looks nationwide without being it.
        cfg["muse_locations"] = locations or LOCATION_OPTIONS
        cfg["muse_pages"] = base.get("muse_pages", 3)
    if "workday" in enabled:
        cfg["workday"] = base.get("workday", [])
        cfg["workday_searches"] = keywords or [""]
    if "jobicy" in enabled:
        cfg["jobicy"] = True
    if "himalayas" in enabled:
        cfg["himalayas"] = True
    if "arbeitnow" in enabled:
        cfg["arbeitnow"] = True
        cfg["arbeitnow_pages"] = 2
    if "usajobs" in enabled:
        email, api_key = usajobs_credentials()
        if email and api_key:
            cfg["usajobs"] = {"email": email, "api_key": api_key, "searches": keywords or [""]}
    if "adzuna" in enabled:
        app_id, app_key = adzuna_credentials()
        if app_id and app_key:
            cfg["adzuna"] = {
                "app_id": app_id,
                "app_key": app_key,
                "searches": keywords or [""],
                # "" is a nationwide pass; named locations are searched in addition.
                "wheres": [""] + [l for l in locations if l and l != "Flexible / Remote"],
                "pages": base.get("adzuna", {}).get("pages", 5),
            }
    return cfg


def fetch(config: dict[str, Any]) -> list[Job]:
    """Fetch every configured source concurrently (blocking wrapper)."""
    if not config:
        return []
    return asyncio.run(fetch_all(config))


def rank(resume: str, jobs: list[Job], **filters) -> list[dict]:
    """Score fetched jobs against the resume. See `rank_jobs` for filter args.

    `rank_jobs` truncates descriptions to 400 chars for its digest output; the web
    app needs the full text to tailor against, so it's restored here.
    """
    ranked = rank_jobs(resume, jobs, **filters)
    full = {j.id: j.description for j in jobs}
    for row in ranked:
        row["description"] = full.get(row["id"], row.get("description", ""))
    return ranked
