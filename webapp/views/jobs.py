"""Step 2 — fetch postings and rank them against the resume."""

from __future__ import annotations

import json

import streamlit as st

from jobapply_mcp import profile
from webapp import nav, search

def _defaults() -> dict:
    """Filter defaults from the config's `watch` block.

    The committed config ships neutral values; a private config.local.json can
    prefill your own. Keywords and locations are never prefilled — those are the
    user's search, not ours.
    """
    watch = search.load_base_config().get("watch") or {}
    return {
        "exclude": ", ".join(watch.get("exclude") or []),
        "exclude_locations": ", ".join(watch.get("exclude_locations") or []),
        "min_salary": int(watch.get("min_salary") or 0),
        "min_score": int(watch.get("min_score") or 15),
        "limit": int(watch.get("limit") or 25),
    }


@st.cache_data(show_spinner=False, ttl=1800)
def _fetch_cached(config_json: str):
    """Cached by the exact config, so re-ranking with new filters is instant."""
    return search.fetch(json.loads(config_json))


def _csv(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def render() -> None:
    st.header("2 · Find matching jobs")

    resume = st.session_state.get("resume_text", "")
    if not resume:
        st.warning("Matching scores need your resume first.")
        if st.button("← Back to Resume", type="primary"):
            nav.goto("Resume")
        return

    d = _defaults()
    derived = profile.derive_search(resume)

    auto = st.toggle(
        "Search from my resume",
        value=True,
        key="search_auto",
        help="Reads the job titles and locations off your resume so you don't "
        "have to type anything. Turn off to set them yourself.",
    )

    if auto:
        titles = ", ".join(derived["keywords"])
        places = ", ".join(derived["locations"])
        if titles or places:
            st.caption(
                f"Using **{titles or 'no titles found'}**"
                + (f" · in **{places}**" if places else " · anywhere")
                + " — from your resume."
            )
        else:
            st.caption(
                "Couldn't read job titles off your resume, so this searches broadly "
                "and ranks everything against it. Turn the toggle off to set terms yourself."
            )

    with st.form("search_form"):
        col1, col2 = st.columns(2)
        with col1:
            if auto:
                keywords = derived["keywords"]
                locations = derived["locations"]
                query = ""
                st.caption("Keywords and locations come from your resume.")
            else:
                keywords = _csv(
                    st.text_input(
                        "Search keywords",
                        key="search_keywords",
                        placeholder="e.g. quality engineer, LLM evaluation, SDET",
                        help="Comma-separated job titles or skills to search for.",
                    )
                )
                locations = st.multiselect(
                    "Locations",
                    options=search.LOCATION_OPTIONS,
                    key="search_locations",
                    placeholder="Choose one or more, or type your own",
                    accept_new_options=True,
                    help="Leave empty to search everywhere, including remote.",
                )
                query = st.text_input(
                    "Required word (optional)",
                    key="search_query",
                    help="Drops any job whose title and description both lack this word.",
                )
        with col2:
            min_score = st.slider("Minimum match score", 0, 100, d["min_score"])
            min_salary = st.number_input(
                "Minimum salary (USD)", min_value=0, max_value=500_000,
                value=d["min_salary"], step=5_000,
                help="Jobs with no listed salary are kept; only known-lower ones are dropped.",
            )
            limit = st.slider("Results to show", 5, 100, d["limit"])

        with st.expander("Exclusions and sources"):
            exclude = _csv(
                st.text_input(
                    "Exclude these words in titles", value=d["exclude"],
                    placeholder="e.g. manufacturing, hardware, sales",
                )
            )
            us_only = st.checkbox(
                "United States only", value=True,
                help="Drops postings that name a country outside the US. Remote "
                "and unspecified locations are kept.",
            )
            exclude_locations = _csv(
                st.text_input(
                    "Also exclude these locations", value=d["exclude_locations"],
                    placeholder="e.g. new york, california",
                )
            )
            enabled = st.multiselect(
                "Sources",
                options=list(search.SOURCE_LABELS),
                default=search.DEFAULT_SOURCES,
                format_func=lambda k: search.SOURCE_LABELS[k],
            )
            if "adzuna" in enabled and not all(search.adzuna_credentials()):
                st.caption(
                    "Adzuna needs `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` in secrets or env — "
                    "it'll be skipped without them. Free keys: developer.adzuna.com"
                )
            if "usajobs" in enabled and not all(search.usajobs_credentials()):
                st.caption(
                    "USAJOBS needs `USAJOBS_EMAIL` / `USAJOBS_API_KEY` in secrets or env — "
                    "it'll be skipped without them. Free keys: developer.usajobs.gov"
                )

        submitted = st.form_submit_button("Search jobs", type="primary")

    if submitted:
        config = search.build_config(enabled, keywords, locations)
        if not config:
            st.error("Select at least one source.")
            return
        if not keywords:
            st.info(
                "Searching broadly and letting the resume match decide. "
                "Add keywords to narrow the pool."
            )
        with st.spinner("Fetching postings from every enabled source…"):
            try:
                jobs = _fetch_cached(json.dumps(config, sort_keys=True))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Fetch failed: {exc}")
                return
        st.session_state.results = search.rank(
            resume,
            jobs,
            query=query or None,
            exclude=exclude,
            exclude_locations=exclude_locations,
            min_salary=min_salary or None,
            us_only=us_only,
            limit=limit,
        )
        st.session_state.min_score = min_score
        st.session_state.fetched_count = len(jobs)

    results = st.session_state.get("results")
    if results is None:
        st.info("Set your filters and hit **Search jobs**.")
        return

    threshold = st.session_state.get("min_score", 0)
    shown = [r for r in results if r["score"] >= threshold]
    st.success(
        f"Fetched {st.session_state.get('fetched_count', 0):,} postings · "
        f"{len(shown)} above a score of {threshold}."
    )
    if shown:
        st.caption("Click a row to read it, then **Select this job & continue** to tailor against it.")

    for job in shown:
        _render_job_card(job)


def _render_job_card(job: dict) -> None:
    salary = job.get("salary") or 0
    bits = [job.get("location") or "location n/a", job.get("source", "")]
    if salary:
        bits.append(f"${int(salary / 1000)}K")
    visa = job.get("visa", "unknown")
    if visa == "sponsors":
        bits.append("sponsors visa")
    elif visa == "no-sponsor":
        bits.append("NO sponsorship")

    title = f"**[{job['score']}]** {job['title'].strip()} — {job['company']}"
    with st.expander(f"{title}  ·  {' · '.join(b for b in bits if b)}"):
        st.markdown(f"[Open the posting]({job['url']})")
        if job.get("matched_keywords"):
            st.caption("Overlap with your resume: " + ", ".join(job["matched_keywords"][:10]))
        if job.get("penalty_flags"):
            st.caption("Flags: " + " · ".join(job["penalty_flags"]))
        st.text(job.get("description", "")[:1200])

        if st.button("Select this job & continue →", type="primary", key=f"select_{job['id']}"):
            st.session_state.selected_job = job
            # Drop any output tailored to the previously selected job.
            st.session_state.pop("tailored_resume", None)
            st.session_state.pop("cover_letter", None)
            nav.goto("Tailor resume")
