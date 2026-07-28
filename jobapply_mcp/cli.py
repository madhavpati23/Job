"""Tiny CLI to exercise the pipeline without Claude/MCP.

  python -m jobapply_mcp.cli search --query python --limit 5
  python -m jobapply_mcp.cli save-resume path/to/resume.txt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import sources, matching, storage


async def _search(args: argparse.Namespace) -> None:
    config = storage.load_config()
    jobs = await sources.fetch_all(config)
    storage.cache_jobs([j.to_dict() for j in jobs])
    print(f"Fetched {len(jobs)} jobs from configured sources.", file=sys.stderr)
    resume = storage.load_resume()
    must = args.must_have.split(",") if args.must_have else None
    excl = args.exclude.split(",") if args.exclude else None
    ranked = matching.rank_jobs(
        resume, jobs, query=args.query, must_have=must,
        exclude=excl, location=args.location, limit=args.limit,
    )
    for r in ranked:
        print(f"[{r['score']:5}] {r['company']:<18} {r['title']}  ({r['source']})")
        print(f"         {r['url']}")


def _save_resume(args: argparse.Namespace) -> None:
    text = open(args.path, encoding="utf-8").read()
    storage.save_resume(text)
    print(f"Saved resume ({len(text)} chars).")


def _apply(args: argparse.Namespace) -> None:
    job = storage.find_cached_job(args.job_id)
    if not job:
        sys.exit(f"No cached job with id {args.job_id!r}. Run a search first.")
    cover = args.cover or storage.find_latest_draft(job)
    if not cover:
        print("[warn] no saved draft found for this job — proceeding without a cover letter.",
              file=sys.stderr)
    print(f"Applying to: {job['title']} @ {job['company']}")
    print(f"  URL:   {job['url']}")
    print(f"  Cover: {cover or '(none)'}")
    from .autofill import run
    asyncio.run(run(job["url"], cover))


async def _watch(args: argparse.Namespace) -> None:
    """Fetch, score, and report only roles not seen on a prior run."""
    config = storage.load_config()
    w = config.get("watch", {})
    jobs = await sources.fetch_all(config)
    storage.cache_jobs([j.to_dict() for j in jobs])

    seen = storage.load_seen()
    all_ids = {j.id for j in jobs}
    fresh = [j for j in jobs if j.id not in seen]

    resume = storage.load_resume()
    ranked = matching.rank_jobs(
        resume, fresh,
        query=w.get("query"),
        exclude=w.get("exclude"),
        location=w.get("location"),
        exclude_locations=w.get("exclude_locations"),
        min_salary=w.get("min_salary"),
        limit=w.get("limit", 15),
    )
    min_score = w.get("min_score", 0)
    new_matches = [r for r in ranked if r["score"] >= min_score]

    storage.save_seen(seen | all_ids)  # remember everything so we only alert once

    if new_matches:
        storage.append_digest(new_matches)
        print(f"{len(new_matches)} new match(es) written to {storage.DIGEST_PATH}")
        for m in new_matches:
            print(f"  [{m['score']:5}] {m['company']:<14} {m['title'].strip()}")
    else:
        scanned = len(fresh)
        print(f"No new matches (scanned {scanned} newly-appeared postings).")


def _mark_applied(args: argparse.Namespace) -> None:
    job = storage.find_cached_job(args.job_id)
    if not job:
        sys.exit(f"No cached job with id {args.job_id!r}. Run a search first.")
    result = storage.mark_applied(job)
    print(f"Logged: {job['title'].strip()} @ {job['company']}"
          + (" (duplicate)" if result["duplicate"] else ""))
    if result["draft_moved_to"]:
        print(f"Draft archived to: {result['draft_moved_to']}")
    print(f"Tracker: {result['log']}")


def main() -> None:
    p = argparse.ArgumentParser(prog="jobapply")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search")
    s.add_argument("--query", default=None)
    s.add_argument("--must-have", default=None, help="comma-separated skills")
    s.add_argument("--exclude", default=None, help="comma-separated words to drop from titles")
    s.add_argument("--location", default=None, help="'remote' or a place substring, e.g. 'texas'")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=lambda a: asyncio.run(_search(a)))

    r = sub.add_parser("save-resume")
    r.add_argument("path")
    r.set_defaults(func=_save_resume)

    a = sub.add_parser("apply", help="open assisted-apply for a job id (uses newest saved draft)")
    a.add_argument("job_id")
    a.add_argument("--cover", default=None, help="override: path to a cover-letter draft")
    a.set_defaults(func=_apply)

    m = sub.add_parser("mark-applied", help="log a submitted application + archive its draft")
    m.add_argument("job_id")
    m.set_defaults(func=_mark_applied)

    w = sub.add_parser("watch", help="fetch + report only NEW matches since last run (for scheduling)")
    w.set_defaults(func=lambda a: asyncio.run(_watch(a)))

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
