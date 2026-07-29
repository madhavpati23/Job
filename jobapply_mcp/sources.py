"""Fetch job openings from public, automation-friendly APIs.

Only sources with real public endpoints are used here — no scraping of
LinkedIn/Indeed, which prohibit automated access.
"""

from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass, asdict
from typing import Any

import httpx

# Some job APIs (e.g. Adzuna) serve an incomplete TLS chain that Python's bundled
# CA store can't complete. Delegating to the OS trust store fixes verification
# without disabling it. Best-effort: skip if truststore isn't available.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

USER_AGENT = "jobapply-mcp/0.1 (personal job search; +https://github.com/)"
TIMEOUT = httpx.Timeout(20.0)


@dataclass
class Job:
    id: str
    source: str
    company: str
    title: str
    location: str
    url: str
    description: str = ""
    salary_min: float = 0.0
    salary_max: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    resp = await client.get(url, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.json()


async def fetch_greenhouse(client: httpx.AsyncClient, token: str) -> list[Job]:
    """Greenhouse public job board API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    try:
        data = await _get_json(client, url)
    except Exception:
        return []
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(
            Job(
                id=f"greenhouse:{token}:{j.get('id')}",
                source="greenhouse",
                company=token,
                title=j.get("title", ""),
                location=(j.get("location") or {}).get("name", ""),
                url=j.get("absolute_url", ""),
                description=_strip_html(j.get("content", "")),
            )
        )
    return jobs


async def fetch_lever(client: httpx.AsyncClient, token: str) -> list[Job]:
    """Lever public postings API."""
    url = f"https://api.lever.co/v0/postings/{token}?mode=json"
    try:
        data = await _get_json(client, url)
    except Exception:
        return []
    jobs = []
    for j in data:
        cats = j.get("categories") or {}
        jobs.append(
            Job(
                id=f"lever:{token}:{j.get('id')}",
                source="lever",
                company=token,
                title=j.get("text", ""),
                location=cats.get("location", ""),
                url=j.get("hostedUrl", ""),
                description=_strip_html(j.get("descriptionPlain") or j.get("description", "")),
            )
        )
    return jobs


async def fetch_ashby(client: httpx.AsyncClient, token: str) -> list[Job]:
    """Ashby public job board API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
    try:
        data = await _get_json(client, url)
    except Exception:
        return []
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(
            Job(
                id=f"ashby:{token}:{j.get('id')}",
                source="ashby",
                company=token,
                title=j.get("title", ""),
                location=j.get("location", ""),
                url=j.get("jobUrl", ""),
                description=_strip_html(j.get("descriptionPlain") or j.get("descriptionHtml", "")),
            )
        )
    return jobs


async def fetch_remoteok(client: httpx.AsyncClient) -> list[Job]:
    """RemoteOK public JSON feed."""
    url = "https://remoteok.com/api"
    try:
        data = await _get_json(client, url)
    except Exception:
        return []
    jobs = []
    for j in data:
        if not isinstance(j, dict) or "id" not in j:
            continue  # first element is legal/metadata
        jobs.append(
            Job(
                id=f"remoteok:{j.get('id')}",
                source="remoteok",
                company=j.get("company", ""),
                title=j.get("position", ""),
                location=j.get("location", "Remote"),
                url=j.get("url", ""),
                description=_strip_html(j.get("description", "")),
            )
        )
    return jobs


async def fetch_remotive(client: httpx.AsyncClient, search: str = "") -> list[Job]:
    """Remotive public API. Supports a search term server-side."""
    url = "https://remotive.com/api/remote-jobs"
    if search:
        url += f"?search={search}"
    try:
        data = await _get_json(client, url)
    except Exception:
        return []
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(
            Job(
                id=f"remotive:{j.get('id')}",
                source="remotive",
                company=j.get("company_name", ""),
                title=j.get("title", ""),
                location=j.get("candidate_required_location", "Remote"),
                url=j.get("url", ""),
                description=_strip_html(j.get("description", "")),
            )
        )
    return jobs


async def fetch_muse(client: httpx.AsyncClient, location: str, pages: int = 1) -> list[Job]:
    """The Muse public API. Supports real location filtering (e.g. 'Austin, TX').

    No keyword search in the public API, so we fetch by location and let the
    scorer/title filters surface relevance. `location` is a city like
    'Austin, TX' or 'Flexible / Remote'.
    """
    jobs: list[Job] = []
    for page in range(pages):
        url = "https://www.themuse.com/api/public/jobs"
        params = {"location": location, "page": page, "descending": "true"}
        try:
            resp = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break
        for j in data.get("results", []):
            locs = ", ".join(l.get("name", "") for l in (j.get("locations") or []))
            jobs.append(
                Job(
                    id=f"muse:{j.get('id')}",
                    source="muse",
                    company=(j.get("company") or {}).get("name", ""),
                    title=j.get("name", ""),
                    location=locs or location,
                    url=(j.get("refs") or {}).get("landing_page", ""),
                    description=_strip_html(j.get("contents", "")),
                )
            )
        if page + 1 >= data.get("page_count", 1):
            break
    return jobs


async def fetch_smartrecruiters(client: httpx.AsyncClient, company: str, limit: int = 50) -> list[Job]:
    """SmartRecruiters public postings API. The list endpoint lacks descriptions,
    so we fetch detail per posting (bounded by `limit`) to get the job text.
    `company` is the SmartRecruiters company identifier (e.g. 'Bosch')."""
    base = f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
    try:
        resp = await client.get(base, params={"limit": limit}, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    async def _detail(posting: dict) -> Job:
        pid = posting.get("id")
        loc = posting.get("location") or {}
        loc_str = ", ".join(x for x in [loc.get("city"), loc.get("region"), loc.get("country")] if x)
        if loc.get("remote"):
            loc_str = (loc_str + " (Remote)").strip()
        desc = ""
        try:
            d = await client.get(f"{base}/{pid}", headers={"User-Agent": USER_AGENT})
            if d.status_code == 200:
                sections = ((d.json().get("jobAd") or {}).get("sections") or {})
                desc = " ".join(_strip_html((sections.get(k) or {}).get("text", ""))
                                for k in ("jobDescription", "qualifications", "additionalInformation"))
        except Exception:
            pass
        return Job(
            id=f"smartrecruiters:{company}:{pid}",
            source="smartrecruiters",
            company=(posting.get("company") or {}).get("name", company),
            title=posting.get("name", ""),
            location=loc_str,
            url=posting.get("ref", "") or f"https://jobs.smartrecruiters.com/{company}/{pid}",
            description=desc,
        )

    postings = data.get("content", [])[:limit]
    return list(await asyncio.gather(*[_detail(p) for p in postings]))


async def fetch_arbeitnow(client: httpx.AsyncClient, pages: int = 2) -> list[Job]:
    """Arbeitnow public job board feed. No key, paginated, heavily EU-weighted."""
    jobs: list[Job] = []
    for page in range(1, pages + 1):
        url = f"https://www.arbeitnow.com/api/job-board-api?page={page}"
        try:
            data = await _get_json(client, url)
        except Exception:
            break
        results = data.get("data", [])
        for j in results:
            remote = " (Remote)" if j.get("remote") else ""
            jobs.append(
                Job(
                    id=f"arbeitnow:{j.get('slug')}",
                    source="arbeitnow",
                    company=j.get("company_name", ""),
                    title=j.get("title", ""),
                    location=f"{j.get('location', '')}{remote}".strip(),
                    url=j.get("url", ""),
                    description=_strip_html(j.get("description", "")),
                )
            )
        if not results:
            break
    return jobs


async def fetch_jobicy(client: httpx.AsyncClient, count: int = 50, geo: str = "") -> list[Job]:
    """Jobicy remote-jobs API. No key. Carries structured salary fields."""
    url = f"https://jobicy.com/api/v2/remote-jobs?count={count}"
    if geo:
        url += f"&geo={geo}"
    try:
        data = await _get_json(client, url)
    except Exception:
        return []
    jobs = []
    for j in data.get("jobs", []):
        # Jobicy reports non-annual salaries too; only annual figures are
        # comparable with the rest of the pipeline.
        annual = str(j.get("salaryPeriod", "")).lower() in ("annual", "yearly", "year", "")
        jobs.append(
            Job(
                id=f"jobicy:{j.get('id')}",
                source="jobicy",
                company=j.get("companyName", ""),
                title=j.get("jobTitle", ""),
                location=j.get("jobGeo", "Remote"),
                url=j.get("url", ""),
                description=_strip_html(j.get("jobDescription") or j.get("jobExcerpt", "")),
                salary_min=float(j.get("salaryMin") or 0) if annual else 0.0,
                salary_max=float(j.get("salaryMax") or 0) if annual else 0.0,
            )
        )
    return jobs


async def fetch_himalayas(client: httpx.AsyncClient, limit: int = 50) -> list[Job]:
    """Himalayas remote-jobs API. No key. Has no per-job id, so the URL is used."""
    url = f"https://himalayas.app/jobs/api?limit={limit}"
    try:
        data = await _get_json(client, url)
    except Exception:
        return []
    jobs = []
    for j in data.get("jobs", []):
        link = j.get("applicationLink") or j.get("guid") or ""
        annual = str(j.get("salaryPeriod", "")).lower() in ("annual", "yearly", "year", "")
        locations = j.get("locationRestrictions") or []
        location = ", ".join(locations) if locations else "Remote"
        jobs.append(
            Job(
                id=f"himalayas:{j.get('guid') or link}",
                source="himalayas",
                company=j.get("companyName", ""),
                title=j.get("title", ""),
                location=location,
                url=link,
                description=_strip_html(j.get("description") or j.get("excerpt", "")),
                salary_min=float(j.get("minSalary") or 0) if annual else 0.0,
                salary_max=float(j.get("maxSalary") or 0) if annual else 0.0,
            )
        )
    return jobs


async def fetch_usajobs(client: httpx.AsyncClient, cfg: dict[str, Any]) -> list[Job]:
    """USAJOBS — every US federal opening. Free key from developer.usajobs.gov.

    Auth is two headers (registered email + API key); returns [] without them.
    """
    email, api_key = cfg.get("email", ""), cfg.get("api_key", "")
    if not email or not api_key:
        return []
    headers = {"Host": "data.usajobs.gov", "User-Agent": email, "Authorization-Key": api_key}
    jobs: list[Job] = []
    for keyword in (cfg.get("searches") or [""]):
        params = {"ResultsPerPage": 100, "Keyword": keyword} if keyword else {"ResultsPerPage": 100}
        try:
            resp = await client.get("https://data.usajobs.gov/api/search",
                                    params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue
        for item in (data.get("SearchResult") or {}).get("SearchResultItems", []):
            d = item.get("MatchedObjectDescriptor") or {}
            pay = (d.get("PositionRemuneration") or [{}])[0]
            summary = (d.get("UserArea") or {}).get("Details", {}).get("JobSummary", "")
            jobs.append(
                Job(
                    id=f"usajobs:{item.get('MatchedObjectId')}",
                    source="usajobs",
                    company=(d.get("OrganizationName") or d.get("DepartmentName") or ""),
                    title=d.get("PositionTitle", ""),
                    location=", ".join(
                        l.get("LocationName", "") for l in (d.get("PositionLocation") or [])
                    )[:120],
                    url=d.get("PositionURI", ""),
                    description=_strip_html(summary or d.get("QualificationSummary", "")),
                    salary_min=float(pay.get("MinimumRange") or 0),
                    salary_max=float(pay.get("MaximumRange") or 0),
                )
            )
    return jobs


async def fetch_adzuna(client: httpx.AsyncClient, cfg: dict[str, Any]) -> list[Job]:
    """Adzuna US aggregator — broad nationwide coverage with keyword + location.

    Requires free app_id/app_key from developer.adzuna.com. Returns [] if unset.
    """
    app_id, app_key = cfg.get("app_id", ""), cfg.get("app_key", "")
    if not app_id or not app_key:
        return []
    jobs: list[Job] = []
    # Support one or more locations: "" = nationwide, plus e.g. "Texas" for a
    # location-priority pass. Backward-compatible with a single "where".
    wheres = cfg.get("wheres") or [cfg.get("where", "")]
    pages = cfg.get("pages", 1)
    for where in wheres:
      for what in (cfg.get("searches") or [""]):
        for page in range(1, pages + 1):
            url = f"https://api.adzuna.com/v1/api/jobs/us/search/{page}"
            params = {
                "app_id": app_id, "app_key": app_key,
                "what": what, "results_per_page": 50, "content-type": "application/json",
            }
            if where:
                params["where"] = where
            try:
                resp = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                break
            results = data.get("results", [])
            for j in results:
                jobs.append(
                    Job(
                        id=f"adzuna:{j.get('id')}",
                        source="adzuna",
                        company=(j.get("company") or {}).get("display_name", ""),
                        title=j.get("title", ""),
                        location=(j.get("location") or {}).get("display_name", ""),
                        url=j.get("redirect_url", ""),
                        description=_strip_html(j.get("description", "")),
                        salary_min=float(j.get("salary_min") or 0),
                        salary_max=float(j.get("salary_max") or 0),
                    )
                )
            if not results:
                break
    return jobs


async def fetch_all(config: dict[str, Any]) -> list[Job]:
    """Fetch from every configured source concurrently."""
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        tasks: list[Any] = []
        for token in config.get("greenhouse", []):
            tasks.append(fetch_greenhouse(client, token))
        for token in config.get("lever", []):
            tasks.append(fetch_lever(client, token))
        for token in config.get("ashby", []):
            tasks.append(fetch_ashby(client, token))
        if config.get("remoteok"):
            tasks.append(fetch_remoteok(client))
        if config.get("remotive"):
            for term in (config.get("remotive_searches") or [""]):
                tasks.append(fetch_remotive(client, term))
        if config.get("muse"):
            pages = config.get("muse_pages", 1)
            for loc in (config.get("muse_locations") or ["Flexible / Remote"]):
                tasks.append(fetch_muse(client, loc, pages))
        for co in config.get("smartrecruiters", []):
            tasks.append(fetch_smartrecruiters(client, co))
        if config.get("arbeitnow"):
            tasks.append(fetch_arbeitnow(client, config.get("arbeitnow_pages", 2)))
        if config.get("jobicy"):
            tasks.append(fetch_jobicy(client))
        if config.get("himalayas"):
            tasks.append(fetch_himalayas(client))
        if config.get("usajobs"):
            tasks.append(fetch_usajobs(client, config["usajobs"]))
        if config.get("adzuna"):
            tasks.append(fetch_adzuna(client, config["adzuna"]))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    jobs: list[Job] = []
    seen: set[str] = set()
    for r in results:
        if not isinstance(r, list):
            continue
        for j in r:
            if j.id in seen:
                continue
            seen.add(j.id)
            jobs.append(j)
    return jobs
