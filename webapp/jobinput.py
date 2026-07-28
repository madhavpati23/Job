"""The 'which job?' control, shared by the tailoring and cover-letter pages.

Both pages need the same posting. Widget keys here are deliberately *not*
namespaced per page: Streamlit renders one page per run, so a shared key is
safe, and it means a description pasted on one page is already there on the
other. Namespacing them made users paste the same posting twice.
"""

from __future__ import annotations

import streamlit as st

SOURCE_KEY = "job_source"
TITLE_KEY = "manual_job_title"
COMPANY_KEY = "manual_job_company"
DESC_KEY = "manual_job_desc"

_PASTE = "Paste a job description"


def manual_job() -> dict | None:
    """The pasted posting, if there is one — independent of which page asks."""
    description = st.session_state.get(DESC_KEY, "")
    if not description.strip():
        return None
    return {
        "id": "manual",
        "title": st.session_state.get(TITLE_KEY, "") or "the role",
        "company": st.session_state.get(COMPANY_KEY, "") or "the company",
        "location": "",
        "url": "",
        "description": description,
    }


def picker() -> dict | None:
    """Render the job selector and return the chosen posting, or None."""
    selected = st.session_state.get("selected_job")

    options = []
    if selected:
        options.append(f"Selected: {selected['title'].strip()} — {selected['company']}")
    options.append(_PASTE)

    # If a posting was pasted earlier, default to that tab rather than resetting.
    if SOURCE_KEY not in st.session_state:
        st.session_state[SOURCE_KEY] = _PASTE if (manual_job() and not selected) else options[0]
    if st.session_state.get(SOURCE_KEY) not in options:
        st.session_state[SOURCE_KEY] = options[0]

    choice = st.radio("Job posting", options, key=SOURCE_KEY, horizontal=True)

    if selected and choice != _PASTE:
        return selected

    col1, col2 = st.columns(2)
    col1.text_input("Job title", key=TITLE_KEY)
    col2.text_input("Company", key=COMPANY_KEY)
    st.text_area(
        "Job description", height=240, key=DESC_KEY,
        placeholder="Paste the full posting here — the more detail, the better the tailoring.",
    )
    job = manual_job()
    if job:
        st.caption("Saved for this session — you won't need to paste it again on the next step.")
    return job
