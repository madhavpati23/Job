"""Job Copilot — upload a resume, find matching jobs, tailor, and write cover letters.

Run locally:   streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from webapp import llm
from webapp.views import jobs, letter, resume, tracker, tailor

st.set_page_config(page_title="Job Copilot", page_icon="🎯", layout="wide")

PAGES = {
    "Resume": resume.render,
    "Find jobs": jobs.render,
    "Tailor resume": tailor.render,
    "Cover letter": letter.render,
    "Tracker": tracker.render,
}


def sidebar() -> str:
    st.sidebar.title("🎯 Job Copilot")
    choice = st.sidebar.radio("Steps", list(PAGES), label_visibility="collapsed")

    st.sidebar.divider()
    st.sidebar.subheader("Status")
    resume_text = st.session_state.get("resume_text", "")
    st.sidebar.write(
        f"Resume: {'✅ ' + st.session_state.get('resume_name', 'loaded') if resume_text else '— none'}"
    )
    selected = st.session_state.get("selected_job")
    st.sidebar.write(
        f"Job: {'✅ ' + selected['company'] if selected else '— none selected'}"
    )

    st.sidebar.divider()
    if llm.api_key():
        st.sidebar.subheader("Anthropic API key")
        st.sidebar.success("Key found in secrets/environment.")
    else:
        # No key configured, so offer one — but make it unmistakably optional.
        # Without the label, first-time visitors read this as a login wall.
        st.sidebar.subheader("Anthropic API key *(optional)*")
        st.sidebar.caption(
            "**Job search, matching, and the cover-letter scaffold all work without "
            "a key.** Add one only to generate a Claude-rewritten resume or a "
            "finished cover letter."
        )
        with st.sidebar.expander("Add a key"):
            st.session_state.user_api_key = st.text_input(
                "Anthropic API key",
                type="password",
                placeholder="sk-ant-…",
                label_visibility="collapsed",
                value=st.session_state.get("user_api_key", ""),
            )
            st.caption(
                "Used for this session only — never stored or logged. "
                "Get one at console.anthropic.com."
            )

    st.sidebar.divider()
    st.sidebar.caption(
        "Job data comes from public APIs (Greenhouse, Lever, Ashby, Remotive, "
        "The Muse, SmartRecruiters, Adzuna). Nothing you upload is stored server-side."
    )
    return choice


def main() -> None:
    choice = sidebar()
    PAGES[choice]()


if __name__ == "__main__":
    main()
