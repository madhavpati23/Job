"""Step 4 — write a cover letter for the selected posting."""

from __future__ import annotations

import streamlit as st

from jobapply_mcp.drafting import build_scaffold
from webapp import llm, resume_io
from webapp.views.tailor import job_picker


def render() -> None:
    st.header("4 · Cover letter")

    resume = st.session_state.get("resume_text", "")
    if not resume:
        st.warning("Add your resume on the **Resume** page first.")
        return

    job = job_picker("letter")
    if not job:
        st.info("Select a job on the **Find jobs** page, or paste a description above.")
        return

    st.divider()
    key = llm.api_key(st.session_state.get("user_api_key", ""))
    notes = st.text_area(
        "Anything to work in? (optional)",
        placeholder="e.g. Mention I've shipped an LLM evaluation platform end to end.",
        key="letter_notes",
    )

    col1, col2 = st.columns(2)
    if col1.button("Write cover letter", type="primary", disabled=not key):
        with st.spinner("Claude is drafting your letter…"):
            try:
                st.session_state.cover_letter = llm.cover_letter(resume, job, key, notes)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Generation failed: {exc}")

    if col2.button("Build scaffold (no API key needed)"):
        st.session_state.cover_letter = build_scaffold(resume, job)

    if not key:
        st.caption(
            "Add an Anthropic API key in the sidebar for a finished letter, or use the "
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
    if st.button("Log this as applied"):
        st.session_state.setdefault("applications", []).append(
            {
                "company": job.get("company", ""),
                "role": job.get("title", "").strip(),
                "location": job.get("location", ""),
                "url": job.get("url", ""),
            }
        )
        st.success("Logged — see the **Tracker** page.")
