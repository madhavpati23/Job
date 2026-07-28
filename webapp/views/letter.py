"""Step 4 — write a cover letter for the selected posting."""

from __future__ import annotations

import streamlit as st

from jobapply_mcp.drafting import build_scaffold
from webapp import jobinput, llm, nav, resume_io


def render() -> None:
    st.header("4 · Cover letter")

    resume = st.session_state.get("resume_text", "")
    if not resume:
        st.warning("Add your resume first.")
        if st.button("← Back to Resume", type="primary"):
            nav.goto("Resume")
        return

    job = jobinput.picker()
    if not job:
        st.info("Paste a job description above, or pick one from search.")
        if st.button("← Find jobs"):
            nav.goto("Find jobs")
        return

    st.divider()
    ready = llm.available()
    notes = st.text_area(
        "Anything to work in? (optional)",
        placeholder="e.g. Mention I've shipped an LLM evaluation platform end to end.",
        key="letter_notes",
    )

    col1, col2 = st.columns(2)
    if col1.button("Write cover letter", type="primary", disabled=not ready):
        with st.spinner("Drafting your letter…"):
            try:
                st.session_state.cover_letter = llm.cover_letter(resume, job, notes)
            except Exception as exc:  # noqa: BLE001
                llm.show_error(exc)

    if col2.button("Build scaffold (no API key needed)"):
        st.session_state.cover_letter = build_scaffold(resume, job)

    if not ready:
        st.caption(
            "Pick an AI provider and add a key in the sidebar for a finished letter, or use the "
            "scaffold — it assembles the real facts and keyword overlap for you to edit."
        )

    letter = st.session_state.get("cover_letter")
    if not letter:
        return

    st.divider()
    st.subheader("Draft")
    edited = st.text_area("Letter", value=letter, height=460, key="letter_editor")
    if edited != letter:
        st.session_state.cover_letter = edited

    slug = f"{job.get('company', 'letter')}".lower().replace(" ", "_")[:30]
    col1, col2 = st.columns(2)
    col1.download_button(
        "Download .md", edited, file_name=f"cover_letter_{slug}.md", mime="text/markdown"
    )
    col2.download_button(
        "Download .docx",
        resume_io.to_docx_bytes(edited),
        file_name=f"cover_letter_{slug}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    st.divider()
    st.markdown("**Applied?** Log it so you can track and export your applications.")
    col1, col2 = st.columns(2)
    if col1.button("Log this as applied & continue →", type="primary"):
        st.session_state.setdefault("applications", []).append(
            {
                "company": job.get("company", ""),
                "role": job.get("title", "").strip(),
                "location": job.get("location", ""),
                "url": job.get("url", ""),
            }
        )
        nav.goto("Tracker")
    with col2:
        nav.next_button("Cover letter", label="Skip to Tracker →", type="secondary")
