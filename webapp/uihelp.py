"""Widgets that stay in sync with the state behind them.

Streamlit ignores a widget's `value=` argument once that widget's key exists in
session_state. So a text area bound to some state and given a key keeps showing
the first value forever: upload a second resume and the editor still displays
the first one, generate a second tailored resume and the box keeps the first.

`bound_text_area` fixes that by detecting when the *source* changed underneath
the widget and resetting the widget to match, while still letting the user's own
typing flow back into the source.
"""

from __future__ import annotations

import streamlit as st


def bound_text_area(label: str, source_key: str, widget_key: str, **kwargs) -> str:
    """A text area two-way bound to `st.session_state[source_key]`.

    Typing updates the source. Replacing the source elsewhere (a new upload, a
    fresh generation) resets the widget, which `value=` alone cannot do.
    """
    source = st.session_state.get(source_key, "") or ""
    stamp_key = f"_{widget_key}_synced"

    # The source changed without the user typing — adopt it.
    if st.session_state.get(stamp_key) != source:
        st.session_state[widget_key] = source
        st.session_state[stamp_key] = source

    edited = st.text_area(label, key=widget_key, **kwargs)

    if edited != source:
        st.session_state[source_key] = edited
        st.session_state[stamp_key] = edited
    return edited


def paste_prompt_block(pasteable: str, where: str, target_label: str) -> None:
    """Offer the assembled prompt for the user to run in their own assistant.

    The app never holds credentials for that assistant — the user is already
    signed in to it, copies the prompt across, and pastes the answer back into
    the editor above. This is the route for people whose subscription covers a
    chat assistant but who have no API credits; it costs a copy-paste and needs
    no key at all.
    """
    with st.expander(f"No API key? Run this in {target_label} yourself", expanded=False):
        st.caption(
            "Copy the prompt, paste it into any assistant you're already signed in to, "
            f"then paste its answer into the {target_label} box above. Nothing here is "
            "sent anywhere by the app, and no login is needed."
        )
        st.code(pasteable, language="markdown")
        st.download_button(
            "Download prompt (.txt)",
            pasteable,
            file_name=f"{where}_prompt.txt",
            mime="text/plain",
            key=f"dl_prompt_{where}",
        )


def job_key(job: dict) -> str:
    """Stable per-posting identity. Falls back for manually-entered jobs, which
    have no source id."""
    return job.get("id") or f"{job.get('company', '')}|{job.get('title', '')}"


def apply_block(job: dict, where: str) -> None:
    """Link out to the posting and let the user log it, on any page that has a job.

    Shared by steps 3 and 4 so applying doesn't require reaching the end of the
    flow: the tailored resume is often all someone needs. `logged_job_key` is
    deliberately not namespaced per page — logging from the tailor step must
    show as logged on the cover-letter step, since it is one application.
    """
    from webapp.views import tracker

    url = (job.get("url") or "").strip()
    company = job.get("company") or "the employer"
    key = job_key(job)
    logged = st.session_state.get("logged_job_key") == key

    if not url and not key.strip("|"):
        return

    st.divider()
    if url:
        st.markdown(f"**Apply at {company}** — opens the posting in a new tab.")
        st.link_button("Open the posting ↗", url, type="primary")
        # Shown in full so the destination is visible before clicking, and so a
        # posting can be copied to another device.
        st.caption(url)
    else:
        st.caption("No link for this posting — it was entered by hand.")

    if logged:
        st.success("Logged in your tracker.")
    elif st.button("Log this as applied", key=f"log_applied_{where}"):
        tracker.add(
            company=job.get("company", ""),
            role=job.get("title", "").strip(),
            location=job.get("location", ""),
            url=url,
        )
        st.session_state["logged_job_key"] = key
        st.rerun()
