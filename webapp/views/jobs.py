"""Step 2 — fetch postings and rank them against the resume."""

from __future__ import annotations

import json
from collections import Counter

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


def _location_options(derived: list[str]) -> list[str]:
    """Metro list, with anywhere the resume named pinned to the top."""
    extra = [l for l in derived if l not in search.LOCATION_OPTIONS]
    return extra + search.LOCATION_OPTIONS


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

    # Adzuna is the only source that searches every US employer. Without it the
    # app still returns jobs, but they come mostly from a fixed set of company
    # boards — which looks like a nationwide search without being one. Say so
    # here rather than in a caption buried inside a collapsed expander.
    if not all(search.adzuna_credentials()):
        st.warning(
            "**Nationwide search is limited.** Results will come mostly from a "
            "fixed set of company career pages. For true US-wide coverage, add "
            "free [Adzuna API keys](https://developer.adzuna.com) as "
            "`ADZUNA_APP_ID` / `ADZUNA_APP_KEY` in app secrets.",
            icon="🌎",
        )

    auto = st.toggle(
        "Search from my resume",
        value=True,
        key="search_auto",
        help="Reads the job titles and locations off your resume so you don't "
        "have to type anything. Turn off to set them yourself.",
    )

    if auto:
        titles = ", ".join(derived["keywords"])
        if titles:
            st.caption(f"Searching for **{titles}** — read from your resume.")
        else:
            st.caption(
                "Couldn't read job titles off your resume, so this searches broadly "
                "and ranks everything against it. Turn the toggle off to set terms yourself."
            )
        # Seed the picker from the resume once, then leave it under the user's
        # control — where someone lives is often not where they want to work.
        if "search_locations" not in st.session_state:
            st.session_state["search_locations"] = derived["locations"]

    with st.form("search_form"):
        # Two questions almost everyone wants to answer, and nothing else.
        # Every other knob sits in Advanced with a working default, because a
        # form with nine controls reads as work to do before you can search.
        col1, col2 = st.columns(2)
        with col1:
            if auto:
                keywords = derived["keywords"]
            else:
                keywords = _csv(
                    st.text_input(
                        "Job titles to search for",
                        key="search_keywords",
                        placeholder="e.g. quality engineer, QA manager, SDET",
                    )
                )
            locations = st.multiselect(
                "Where do you want to work?",
                options=_location_options(derived["locations"]),
                key="search_locations",
                placeholder="Any location (including remote)",
                accept_new_options=True,
                help="Only these places, plus remote jobs. Leave empty for anywhere in the US.",
            )
        with col2:
            min_salary = st.number_input(
                "Minimum salary (USD)", min_value=0, max_value=500_000,
                value=d["min_salary"], step=5_000,
                help="Jobs that don't list a salary are still shown.",
            )
            limit = st.slider("How many results?", 5, 100, d["limit"])

        with st.expander("Advanced options"):
            us_only = st.checkbox(
                "United States only", value=True, key="search_us_only",
                help="Drops postings that name a country outside the US. Remote "
                "and unspecified locations are kept.",
            )
            min_score = st.slider(
                "Minimum match score", 0, 100, d["min_score"],
                help="How closely a job must match your resume. Lower to see more.",
            )
            exclude = _csv(
                st.text_input(
                    "Skip jobs whose title contains", value=d["exclude"],
                    placeholder="e.g. manufacturing, hardware, sales",
                )
            )
            companies = _csv(
                st.text_input(
                    "Also search these companies by name",
                    key="search_companies",
                    placeholder="e.g. Figma, Discord, Stripe",
                    help="Pulled straight from their careers page, on top of the "
                    "nationwide search. Anything not found is skipped.",
                )
            )
            query = st.text_input(
                "Must contain this word",
                key="search_query",
                placeholder="optional",
                help="Drops any job whose title and description both lack this word.",
            )

            pick_sources = st.checkbox(
                f"Choose job sources myself ({len(search.DEFAULT_SOURCES)} used by default)",
                value=False, key="search_pick_sources",
            )
            if pick_sources:
                enabled = st.multiselect(
                    "Sources",
                    options=list(search.SOURCE_LABELS),
                    default=search.DEFAULT_SOURCES,
                    format_func=lambda k: search.SOURCE_LABELS[k],
                )
            else:
                enabled = search.DEFAULT_SOURCES
            if "usajobs" in enabled and not all(search.usajobs_credentials()):
                st.caption(
                    "USAJOBS needs `USAJOBS_EMAIL` / `USAJOBS_API_KEY` in secrets or env — "
                    "it'll be skipped without them. Free keys: developer.usajobs.gov"
                )

        submitted = st.form_submit_button("Search jobs", type="primary")

    if submitted:
        config = search.build_config(enabled, keywords, locations, companies)
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
            min_salary=min_salary or None,
            us_only=us_only,
            locations=locations,
            limit=limit,
        )
        st.session_state.min_score = min_score
        st.session_state.fetched_count = len(jobs)
        st.session_state.source_counts = Counter(j.source for j in jobs)
        st.session_state.employer_count = len({j.company.lower() for j in jobs if j.company})

    results = st.session_state.get("results")
    if results is None:
        st.info("Set your filters and hit **Search jobs**.")
        return

    threshold = st.session_state.get("min_score", 0)
    shown = [r for r in results if r["score"] >= threshold]
    employers = st.session_state.get("employer_count", 0)
    st.success(
        f"Fetched {st.session_state.get('fetched_count', 0):,} postings from "
        f"{employers:,} employers · {len(shown)} above a score of {threshold}."
    )
    counts = st.session_state.get("source_counts")
    if counts:
        # Where results came from decides how much breadth they really represent,
        # so it shouldn't take reading the code to find out.
        breakdown = " · ".join(
            f"{search.SOURCE_LABELS.get(k, k)}: {v:,}" for k, v in counts.most_common()
        )
        st.caption(f"Sources — {breakdown}")
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
