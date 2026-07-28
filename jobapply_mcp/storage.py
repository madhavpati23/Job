"""On-disk state: config, cached resume, cached jobs, and application drafts."""

from __future__ import annotations

import csv
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DRAFTS = ROOT / "drafts"
SUBMITTED = DRAFTS / "submitted"
CONFIG_PATH = ROOT / "config.json"
# Your real search targets go here. It's gitignored, so the committed config.json
# can stay a generic example while your actual company list, salary floor, and
# filters stay private. Takes precedence when present.
LOCAL_CONFIG_PATH = ROOT / "config.local.json"
RESUME_PATH = DATA / "resume.txt"
JOBS_CACHE = DATA / "jobs_cache.json"
SEEN_PATH = DATA / "seen_jobs.json"
DIGEST_PATH = ROOT / "new_matches.md"
APPLICATIONS_LOG = ROOT / "applications.csv"


def _ensure_dirs() -> None:
    DATA.mkdir(exist_ok=True)
    DRAFTS.mkdir(exist_ok=True)


def load_config() -> dict[str, Any]:
    """Load config.local.json if you have one, else the committed config.json."""
    for path in (LOCAL_CONFIG_PATH, CONFIG_PATH):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
    return {"remoteok": True}


def save_resume(text: str) -> None:
    _ensure_dirs()
    RESUME_PATH.write_text(text, encoding="utf-8")


def load_resume() -> str:
    return RESUME_PATH.read_text(encoding="utf-8") if RESUME_PATH.exists() else ""


def cache_jobs(jobs: list[dict]) -> None:
    _ensure_dirs()
    JOBS_CACHE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def load_cached_jobs() -> list[dict]:
    if JOBS_CACHE.exists():
        return json.loads(JOBS_CACHE.read_text(encoding="utf-8"))
    return []


def find_cached_job(job_id: str) -> dict | None:
    for j in load_cached_jobs():
        if j.get("id") == job_id:
            return j
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def save_draft(job: dict, body: str) -> str:
    """Write an application draft to drafts/ and return its path."""
    _ensure_dirs()
    name = f"{_slug(job.get('company',''))}-{_slug(job.get('title',''))}-{int(time.time())}.md"
    path = DRAFTS / name
    header = (
        f"# Application draft\n\n"
        f"- **Company:** {job.get('company','')}\n"
        f"- **Role:** {job.get('title','')}\n"
        f"- **Location:** {job.get('location','')}\n"
        f"- **Apply at:** {job.get('url','')}\n"
        f"- **Source:** {job.get('source','')}\n\n"
        f"---\n\n"
    )
    path.write_text(header + body, encoding="utf-8")
    return str(path)


def find_latest_draft(job: dict) -> str | None:
    """Return the path to the newest draft saved for this job, if any.

    Drafts are named "<company-slug>-<title-slug>-<ts>.md", so we match on the
    company+title prefix and pick the most recently modified.
    """
    prefix = f"{_slug(job.get('company',''))}-{_slug(job.get('title',''))}-"
    matches = [p for p in DRAFTS.glob("*.md") if p.name.startswith(prefix)]
    if not matches:
        return None
    return str(max(matches, key=lambda p: p.stat().st_mtime))


def mark_applied(job: dict) -> dict:
    """Record an application: move its draft to drafts/submitted/ and log a row.

    Idempotent-ish: if already logged, it still moves any lingering draft and
    notes the duplicate. Returns a summary dict.
    """
    _ensure_dirs()
    SUBMITTED.mkdir(exist_ok=True)

    job_id = job.get("id", "")
    already = any(r.get("job_id") == job_id for r in load_applications())

    moved_to = None
    draft = find_latest_draft(job)
    if draft:
        src = Path(draft)
        dest = SUBMITTED / src.name
        src.replace(dest)
        moved_to = str(dest)

    new_log = not APPLICATIONS_LOG.exists()
    with APPLICATIONS_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_log:
            w.writerow(["date", "job_id", "company", "role", "location", "url", "status"])
        w.writerow([
            date.today().isoformat(), job_id, job.get("company", ""),
            (job.get("title", "") or "").strip(), job.get("location", ""),
            job.get("url", ""), "applied",
        ])

    return {
        "job_id": job_id,
        "logged": True,
        "duplicate": already,
        "draft_moved_to": moved_to,
        "log": str(APPLICATIONS_LOG),
    }


def load_seen() -> set[str]:
    if SEEN_PATH.exists():
        return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
    return set()


def save_seen(ids: set[str]) -> None:
    _ensure_dirs()
    SEEN_PATH.write_text(json.dumps(sorted(ids)), encoding="utf-8")


def append_digest(new_matches: list[dict]) -> None:
    """Prepend a timestamped block of new matches to new_matches.md."""
    from datetime import datetime
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"## {stamp} — {len(new_matches)} new match(es)\n"]
    for m in new_matches:
        visa = m.get("visa", "unknown")
        visa_tag = {"sponsors": " · ✅ sponsors visa", "no-sponsor": " · ❌ no sponsorship"}.get(visa, "")
        sal = m.get("salary", 0) or 0
        sal_tag = f" · 💰 ${int(sal/1000)}K" if sal else ""
        # `apply` resolves aggregator links and detects the ATS, so the command
        # works for any source — it autofills structured forms (Greenhouse/Lever/
        # Ashby/Workable) and opens the rest for manual completion.
        structured = m.get("source") in ("greenhouse", "lever", "ashby")
        hint = "autofills" if structured else "opens form; may need manual fill"
        lines.append(
            f"- **[{m['score']}]** {m['title'].strip()} @ {m['company']} "
            f"({m.get('location','') or 'n/a'}){sal_tag}{visa_tag}  \n"
            f"  {m['url']}  \n"
            f"  apply: `python -m jobapply_mcp.cli apply {m['id']}`  ({hint})"
        )
    block = "\n".join(lines) + "\n\n"
    prior = DIGEST_PATH.read_text(encoding="utf-8") if DIGEST_PATH.exists() else "# New job matches\n\n"
    # keep the H1 at top, insert newest block right after it
    if prior.startswith("# New job matches"):
        head, _, rest = prior.partition("\n\n")
        DIGEST_PATH.write_text(f"{head}\n\n{block}{rest}", encoding="utf-8")
    else:
        DIGEST_PATH.write_text(f"# New job matches\n\n{block}{prior}", encoding="utf-8")


def load_applications() -> list[dict]:
    if not APPLICATIONS_LOG.exists():
        return []
    with APPLICATIONS_LOG.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def list_drafts() -> list[dict]:
    _ensure_dirs()
    out = []
    for p in sorted(DRAFTS.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        out.append({"file": p.name, "path": str(p), "modified": int(p.stat().st_mtime)})
    return out
