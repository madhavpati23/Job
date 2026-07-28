"""Step 3 — rewrite the resume against one specific posting."""

from __future__ import annotations

import streamlit as st

from webapp import llm, nav, resume_io


def job_picker(key_prefix: str) -> dict | None:
    """Shared control: use the job selected on the search page, or paste one.

    Returns a job dict (title/company/location/description) or None.
    """
    selected = st.session_state.get("selected_job")
    options = ["Paste a job description"]
    if selected:
        options.insert(0, f"Selected: {selected['title'].strip()} — {selected['company']}")

    choice = st.radio("Job posting", options, key=f"{key_prefix}_source", horizontal=True)

    if selected and choice.startswith("Selected:"):
        return selected

    col1, col2 = st.columns(2)
    title = col1.text_input("Job title", key=f"{key_prefix}_title")
    company = col2.text_input("Company", key=f"{key_prefix}_company")
    description = st.text_area(
        "Job description", height=240, key=f"{key_prefix}_desc",
        placeholder="Paste the full posting here — the more detail, the better the tailoring.",
    )
    if not description.strip():
        return None
    return {
        "id": "manual",
        "title": title or "the role",
        "company": company or "the company",
        "location": "",
        "url": "",
        "description": description,
    }


def show_gap_analysis(resume: str, job: dict) -> None:
    gaps = llm.gap_analysis(resume, job.get("description", ""), job.get("company", ""))
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Posting keywords your resume already covers**")
        st.success(", ".join(gaps["covered"]) or "none detected")
    with col2:
        st.markdown("**Keywords missing from your resume**")
        st.warning(", ".join(gaps["missing"]) or "none")
    st.caption(
        "Missing keywords are worth addressing only where you genuinely have the "
        "experience. Don't add anything you can't back up in an interview."
    )


def render() -> None:
    st.header("3 · Tailor your resume")

    resume = st.session_state.get("resume_text", "")
    if not resume:
        st.warning("Add your resume first.")
        if st.button("← Back to Resume", type="primary"):
            nav.goto("Resume")
        return

    job = job_picker("tailor")
    if not job:
        st.info("Paste a job description above, or pick one from search.")
        if st.button("← Find jobs"):
            nav.goto("Find jobs")
        return

    st.divider()
    show_gap_analysis(resume, job)
    st.divider()

    ready = llm.available()
    notes = st.text_area(
        "Anything else to emphasize? (optional)",
        placeholder="e.g. Lead with the AI evaluation work; keep it to one page.",
        key="tailor_notes",
    )

    if not ready:
        st.info(
            "Pick an AI provider and add a key in the sidebar to generate a rewritten resume. "
            "Without one, use the gap analysis above to edit manually — then continue."
        )
        nav.next_button("Tailor resume", key="next_tailor_nokey")
        return

    if st.button("Generate tailored resume", type="primary"):
        with st.spinner("Rewriting your resume for this posting…"):
            try:
                st.session_state.tailored_resume = llm.tailor_resume(resume, job, notes)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Generation failed: {exc}")

    tailored = st.session_state.get("tailored_resume")
    if not tailored:
        return

    st.divider()
    st.subheader("Tailored resume")
    st.caption("Edit freely before downloading — you are the final check on every claim.")
    edited = st.text_area("Result", value=tailored, height=520, key="tailored_editor")
    if edited != tailored:
        st.session_state.tailored_resume = edited

    slug = f"{job.get('company', 'resume')}".lower().replace(" ", "_")[:30]
    col1, col2 = st.columns(2)
    col1.download_button(
        "Download .md", edited, file_name=f"resume_{slug}.md", mime="text/markdown"
    )
    col2.download_button(
        "Download .docx",
        resume_io.to_docx_bytes(edited),
        file_name=f"resume_{slug}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    st.divider()
    nav.next_button("Tailor resume")
