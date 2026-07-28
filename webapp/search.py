"""Job fetching + ranking for the web app.

Wraps the existing `jobapply_mcp` source and scoring modules. Those are pure
functions over data, so they're reused unchanged; only the config assembly and
caching layer is web-specific.
"""

from __future__ import annotations

import asyncio
import os
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
    "adzuna": "Adzuna (nationwide US)",
}


def load_base_config() -> dict[str, Any]:
    """Board lists and search terms, preferring a private config.local.json."""
    return load_config()


def adzuna_credentials() -> tuple[str, str]:
    """Adzuna keys come from secrets/env only — never from the committed config."""
    app_id, app_key = os.environ.get("ADZUNA_APP_ID", ""), os.environ.get("ADZUNA_APP_KEY", "")
    if app_id and app_key:
        return app_id, app_key
    try:
        import streamlit as st

        return str(st.secrets.get("ADZUNA_APP_ID", "")), str(st.secrets.get("ADZUNA_APP_KEY", ""))
    except Exception:
        return "", ""


def build_config(enabled: list[str], keywords: list[str], locations: list[str]) -> dict[str, Any]:
    """Assemble a `fetch_all` config from the user's UI selections."""
    base = load_base_config()
    cfg: dict[str, Any] = {}

    for name in ("greenhouse", "lever", "ashby"):
        if name in enabled:
            cfg[name] = base.get(name, [])
    if "smartrecruiters" in enabled:
        cfg["smartrecruiters"] = base.get("smartrecruiters", [])
    if "remoteok" in enabled:
        cfg["remoteok"] = True
    if "remotive" in enabled:
        cfg["remotive"] = True
        cfg["remotive_searches"] = keywords or base.get("remotive_searches") or [""]
    if "muse" in enabled:
        cfg["muse"] = True
        cfg["muse_locations"] = locations or base.get("muse_locations") or ["Flexible / Remote"]
        cfg["muse_pages"] = base.get("muse_pages", 2)
    if "adzuna" in enabled:
        app_id, app_key = adzuna_credentials()
        if app_id and app_key:
            cfg["adzuna"] = {
                "app_id": app_id,
                "app_key": app_key,
                "searches": keywords or ["quality engineer"],
                "wheres": [""] + [l for l in locations if l],
                "pages": base.get("adzuna", {}).get("pages", 2),
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
