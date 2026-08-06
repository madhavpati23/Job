"""Step 4 — write a cover letter for the selected posting."""

from __future__ import annotations

import streamlit as st

from jobapply_mcp.drafting import build_scaffold
from webapp import aihint, jobinput, llm, nav, resume_io, uihelp
from webapp.views import tracker


def render() -> None:
    nav.back_button("Cover letter")
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

    if ready:
        aihint.ready_badge()
        notes = st.text_area(
            "Anything to work in? (optional)",
            placeholder="e.g. Mention I've shipped an LLM evaluation platform end to end.",
            key="letter_notes",
        )
        col1, col2 = st.columns(2)
        if col1.button("Write cover letter", type="primary"):
            with st.spinner("Drafting your letter…"):
                try:
                    st.session_state.cover_letter = llm.cover_letter(resume, job, notes)
                except Exception as exc:  # noqa: BLE001
                    llm.show_error(exc)
        if col2.button("Build scaffold instead"):
            st.session_state.cover_letter = build_scaffold(resume, job)
    else:
        # The scaffold is genuinely useful here, so lead with it rather than
        # making the whole step look blocked.
        aihint.setup_callout("write a finished cover letter")
        st.markdown("#### Or start from a scaffold — no key needed")
        st.caption(
            "Assembles the posting's real keywords and your matching experience "
            "into a structure you fill in yourself."
        )
        if st.button("Build scaffold", type="primary"):
            st.session_state.cover_letter = build_scaffold(resume, job)

    letter = st.session_state.get("cover_letter")
    if not letter:
        return

    st.divider()
    st.subheader("Draft")
    edited = uihelp.bound_text_area("Letter", "cover_letter", "letter_editor", height=460)

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

    # Logging used to jump straight to the Tracker, which hid the apply link
    # below before it could be used. It now stays put and confirms in place, so
    # the page still works if you log first and apply second.
    job_key = job.get("id") or f"{job.get('company', '')}|{job.get('title', '')}"
    logged = st.session_state.get("logged_job_key") == job_key

    col1, col2 = st.columns(2)
    if logged:
        col1.success("Logged in your tracker.")
    elif col1.button("Log this as applied", type="primary"):
        tracker.add(
            company=job.get("company", ""),
            role=job.get("title", "").strip(),
            location=job.get("location", ""),
            url=job.get("url", ""),
        )
        st.session_state["logged_job_key"] = job_key
        st.rerun()
    with col2:
        nav.next_button("Cover letter", label="Go to Tracker →", kind="secondary")

    apply_url = (job.get("url") or "").strip()
    if apply_url:
        st.divider()
        company = job.get("company") or "the employer"
        st.markdown(f"**Apply at {company}** — opens the posting in a new tab.")
        st.link_button("Open the posting ↗", apply_url, type="primary")
        # Shown in full so the destination is visible before clicking, and so a
        # manually-entered posting can be copied to another device.
        st.caption(apply_url)

    st.divider()
    if st.button("Apply to another position →"):
        nav.start_new_application()
