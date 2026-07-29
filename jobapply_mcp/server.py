"""MCP server exposing job-search and application-drafting tools to Claude.

Run standalone:  python -m jobapply_mcp.server
Register in claude_desktop_config.json (see README) to use inside Claude.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from . import sources, matching, storage, drafting

mcp = FastMCP("jobapply")


@mcp.tool()
def save_resume(text: str) -> str:
    """Store the user's resume text so future searches can be scored against it.

    Args:
        text: Full plain-text resume.
    """
    storage.save_resume(text)
    return f"Resume saved ({len(text)} chars)."


@mcp.tool()
def get_resume() -> str:
    """Return the currently stored resume text, or empty if none saved."""
    return storage.load_resume() or "(no resume saved yet — call save_resume first)"


@mcp.tool()
async def search_jobs(
    query: str = "",
    must_have: list[str] | None = None,
    exclude: list[str] | None = None,
    location: str | None = None,
    limit: int = 10,
    refresh: bool = True,
) -> str:
    """Search configured job boards and return openings ranked by fit to the resume.

    Args:
        query: Optional keyword to filter titles/descriptions (e.g. "qa", "llm").
        must_have: Optional skills that should appear in the posting; missing ones lower the score.
        exclude: Words that, if in the title, drop the job (e.g. ["manufacturing", "hardware"]).
        location: "remote" to keep remote/anywhere roles, or a place substring like "texas".
        limit: Max results to return.
        refresh: Fetch live from the boards (True) or use the last cached pull (False).
    """
    if refresh:
        config = storage.load_config()
        jobs = await sources.fetch_all(config)
        storage.cache_jobs([j.to_dict() for j in jobs])
    else:
        jobs = [sources.Job(**{k: j.get(k, "") for k in sources.Job.__dataclass_fields__}) for j in storage.load_cached_jobs()]

    resume = storage.load_resume()
    ranked = matching.rank_jobs(
        resume, jobs, query=query or None, must_have=must_have,
        exclude=exclude, location=location, limit=limit,
    )
    return json.dumps(
        {
            "count": len(ranked),
            "scored_against_resume": bool(resume),
            "results": ranked,
        },
        indent=2,
    )


@mcp.tool()
def get_job(job_id: str) -> str:
    """Return the full cached description for one job id (from a prior search_jobs)."""
    job = storage.find_cached_job(job_id)
    if not job:
        return f"No cached job with id {job_id!r}. Run search_jobs first."
    return json.dumps(job, indent=2)


@mcp.tool()
def draft_application(job_id: str) -> str:
    """Build a tailored cover-letter scaffold for a job, grounded in the resume.

    Returns a starter draft (markdown) with the posting's keywords, which of them
    match the resume, and which don't. Claude should refine this into final prose,
    then call save_draft to persist it. Does NOT submit anything.

    Args:
        job_id: id from a prior search_jobs result.
    """
    job = storage.find_cached_job(job_id)
    if not job:
        return f"No cached job with id {job_id!r}. Run search_jobs first."
    resume = storage.load_resume()
    if not resume:
        return "No resume saved. Call save_resume first."
    return drafting.build_scaffold(resume, job)


@mcp.tool()
def save_draft(job_id: str, body: str) -> str:
    """Save a tailored application/cover-letter draft for a job. Does NOT submit anything.

    Args:
        job_id: id from a prior search_jobs result.
        body: The tailored cover letter / application text you (Claude) wrote.
    """
    job = storage.find_cached_job(job_id)
    if not job:
        return f"No cached job with id {job_id!r}. Run search_jobs first."
    path = storage.save_draft(job, body)
    return f"Draft saved to {path}. The user must review and submit it manually at {job.get('url','')}."


@mcp.tool()
def list_drafts() -> str:
    """List application drafts prepared so far (not yet submitted)."""
    return json.dumps(storage.list_drafts(), indent=2)


@mcp.tool()
def mark_applied(job_id: str) -> str:
    """Record that you submitted an application. Run this AFTER you click Submit.

    Moves the job's draft into drafts/submitted/ and appends a row to
    applications.csv (your application tracker). Does not submit anything itself.

    Args:
        job_id: id from a prior search_jobs result.
    """
    job = storage.find_cached_job(job_id)
    if not job:
        return f"No cached job with id {job_id!r}. Run search_jobs first."
    result = storage.mark_applied(job)
    note = " (already logged before — duplicate row added)" if result["duplicate"] else ""
    moved = f"\nDraft archived to: {result['draft_moved_to']}" if result["draft_moved_to"] else ""
    return f"Logged application for {job.get('title','').strip()} @ {job.get('company','')}{note}.{moved}"


@mcp.tool()
def list_applications() -> str:
    """List all applications you've marked as submitted (your tracker)."""
    return json.dumps(storage.load_applications(), indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
