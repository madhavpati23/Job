"""Step 2 — fetch postings and rank them against the resume."""

from __future__ import annotations

import json

import streamlit as st

from webapp import search

DEFAULT_EXCLUDE = "manufacturing, hardware, electrical, mechanical, sales, account"
DEFAULT_EXCLUDE_LOCATIONS = (
    "india, united kingdom, ireland, australia, japan, canada, germany, "
    "singapore, mexico, philippines, brazil, poland, portugal, spain, france"
)


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
        st.warning("Add your resume on the **Resume** page first — matching scores need it.")
        return

    with st.form("search_form"):
        col1, col2 = st.columns(2)
        with col1:
            keywords = _csv(
                st.text_input(
                    "Search keywords",
                    value="AI evaluation, LLM evaluation, quality engineer, QA",
                    help="Comma-separated. Used by the keyword-searchable sources.",
                )
            )
            locations = _csv(
                st.text_input(
                    "Locations",
                    value="Austin, TX, Dallas, TX, Flexible / Remote",
                    help="Comma-separated cities for The Muse and Adzuna.",
                )
            )
            query = st.text_input(
                "Required word (optional)",
                help="Drops any job whose title and description both lack this word.",
            )
        with col2:
            min_score = st.slider("Minimum match score", 0, 100, 15)
            min_salary = st.number_input(
                "Minimum salary (USD)", min_value=0, max_value=500_000, value=135_000, step=5_000,
                help="Jobs with no listed salary are kept; only known-lower ones are dropped.",
            )
            limit = st.slider("Results to show", 5, 100, 25)

        with st.expander("Exclusions and sources"):
            exclude = _csv(st.text_input("Exclude these words in titles", value=DEFAULT_EXCLUDE))
            exclude_locations = _csv(
                st.text_input("Exclude these locations", value=DEFAULT_EXCLUDE_LOCATIONS)
            )
            enabled = st.multiselect(
                "Sources",
                options=list(search.SOURCE_LABELS),
                default=["greenhouse", "lever", "ashby", "remotive", "muse", "adzuna"],
                format_func=lambda k: search.SOURCE_LABELS[k],
            )
            if "adzuna" in enabled and not all(search.adzuna_credentials()):
                st.caption(
                    "Adzuna needs `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` in secrets or env — "
                    "it'll be skipped without them. Free keys: developer.adzuna.com"
                )

        submitted = st.form_submit_button("Search jobs", type="primary")

    if submitted:
        config = search.build_config(enabled, keywords, locations)
        if not config:
            st.error("Select at least one source.")
            return
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

        if st.button("Select this job", key=f"select_{job['id']}"):
            st.session_state.selected_job = job
            st.session_state.pop("tailored_resume", None)
            st.session_state.pop("cover_letter", None)
            st.success(f"Selected. Head to **Tailor resume** or **Cover letter**.")
