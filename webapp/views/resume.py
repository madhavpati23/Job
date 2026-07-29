"""Step 1 — upload or paste a resume."""

from __future__ import annotations

import streamlit as st

from webapp import nav, resume_io, uihelp


def _adopt(text: str, name: str) -> None:
    """Install a new resume and discard anything derived from the previous one.

    A tailored resume or cover letter written against the old resume is not just
    stale — the change-diff would compare the new resume to the old rewrite and
    report nonsense.
    """
    previous = st.session_state.get("resume_text", "")
    st.session_state.resume_text = text
    st.session_state.resume_name = name
    if previous and previous != text:
        for key in ("tailored_resume", "cover_letter", "tailored_editor", "letter_editor"):
            st.session_state.pop(key, None)


def render() -> None:
    st.header("1 · Your resume")
    st.caption(
        "Everything stays in your browser session — nothing is written to disk or "
        "shared between visitors."
    )

    tab_upload, tab_paste = st.tabs(["Upload a file", "Paste text"])

    with tab_upload:
        uploaded = st.file_uploader(
            "Resume file",
            type=list(resume_io.SUPPORTED),
            help="PDF, DOCX, TXT, or Markdown. Scanned/image PDFs won't extract — paste instead.",
        )
        if uploaded is not None and st.button("Extract text", type="primary"):
            try:
                text = resume_io.extract_text(uploaded)
            except ValueError as exc:
                st.error(str(exc))
            else:
                _adopt(text, uploaded.name)
                st.success(f"Extracted {len(text):,} characters.")

    with tab_paste:
        pasted = st.text_area("Paste your resume", height=260, key="paste_box")
        if st.button("Use this text") and pasted.strip():
            _adopt(pasted.strip(), "pasted")
            st.success("Resume saved.")

    resume = st.session_state.get("resume_text", "")
    if not resume:
        st.info("Add a resume to unlock job search, tailoring, and cover letters.")
        return

    st.divider()
    st.subheader("Review and edit")
    st.caption(
        "Extraction from PDFs is imperfect. Clean this up now — every later step "
        "reads from this text."
    )
    edited = uihelp.bound_text_area(
        "Resume text", "resume_text", "resume_editor", height=420
    )

    col1, col2 = st.columns(2)
    col1.metric("Characters", f"{len(edited):,}")
    col2.metric("Words", f"{len(edited.split()):,}")

    st.divider()
    st.markdown("**Looks right?** Next we'll search live job boards and rank them against this.")
    nav.next_button("Resume")
