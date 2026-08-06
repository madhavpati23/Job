"""Step navigation shared by the sidebar and the in-page Next buttons.

Streamlit forbids writing to a widget's session_state key after that widget has
been instantiated in the same run — and the sidebar radio renders before any
page body. So a Next button can't set the radio directly. It stages the target
in `_goto` and reruns; `apply_pending()` consumes it at the top of the next run,
before the radio is created.
"""

from __future__ import annotations

import streamlit as st

STEPS = ["Resume", "Find jobs", "Tailor resume", "Cover letter", "Tracker"]
NAV_KEY = "nav"
_PENDING = "_goto"


def apply_pending() -> None:
    """Consume a staged destination. Call before the nav widget is created."""
    target = st.session_state.pop(_PENDING, None)
    if target in STEPS:
        st.session_state[NAV_KEY] = target


def goto(step: str) -> None:
    """Stage `step` as the next page and rerun."""
    st.session_state[_PENDING] = step
    st.rerun()


def progress() -> dict[str, str]:
    """Per-step state: 'done', 'locked', or '' (available, not yet done).

    Doubles as the app's status display, so it reads what the steps actually
    depend on rather than a separate hand-maintained summary.
    """
    from webapp import jobinput

    resume = bool(st.session_state.get("resume_text"))
    job = bool(st.session_state.get("selected_job") or jobinput.manual_job())

    def state(done: bool, unlocked: bool) -> str:
        if not unlocked:
            return "locked"
        return "done" if done else ""

    return {
        "Resume": state(resume, True),
        "Find jobs": state(job, resume),
        "Tailor resume": state(bool(st.session_state.get("tailored_resume")), resume and job),
        "Cover letter": state(bool(st.session_state.get("cover_letter")), resume and job),
        "Tracker": state(bool(st.session_state.get("applications")), True),
    }


_ICONS = {"done": "✅", "locked": "🔒", "": "○"}


def step_label(step: str, states: dict[str, str]) -> str:
    """'✅ 1 · Resume' — number, state, and name in one line.

    `states` is passed in rather than read from session_state: Streamlit calls
    a widget's format_func outside the script run when resolving widget state,
    where session_state isn't available.
    """
    icon = _ICONS.get(states.get(step, ""), "○")
    return f"{icon}  {STEPS.index(step) + 1} · {step}"


# Cleared when starting a new application: everything tied to one posting.
# Deliberately excludes the resume, the search results, the tracker, and the AI
# settings — re-uploading a resume or re-running a search to apply to a second
# job would be the app wasting the user's time.
_PER_JOB_KEYS = (
    "selected_job",
    "tailored_resume",
    "cover_letter",
    "tailor_notes",
    "letter_notes",
    "tailored_editor",
    "letter_editor",
    "job_source",
    "logged_job_key",
    "manual_job_title",
    "manual_job_company",
    "manual_job_desc",
)


def start_new_application(destination: str = "Find jobs") -> None:
    """Drop everything specific to the last posting and go pick another."""
    for key in _PER_JOB_KEYS:
        st.session_state.pop(key, None)
    goto(destination)


def next_step(current: str) -> str | None:
    idx = STEPS.index(current)
    return STEPS[idx + 1] if idx + 1 < len(STEPS) else None


def prev_step(current: str) -> str | None:
    idx = STEPS.index(current)
    return STEPS[idx - 1] if idx > 0 else None


def back_button(current: str, key: str | None = None) -> None:
    """Render a '← <step>' link at the top of a page.

    Steps are ordered, so 'back' is the previous step rather than a browser-style
    history: returning to wherever you last were would be unpredictable when the
    sidebar can jump anywhere. The first step has nowhere to go and renders nothing.
    """
    prev = prev_step(current)
    if not prev:
        return
    if st.button(f"←  {prev}", type="tertiary", key=key or f"back_{current}"):
        goto(prev)


def next_button(
    current: str,
    label: str | None = None,
    key: str | None = None,
    kind: str = "primary",
) -> None:
    """Render a 'Next: <step>' button that advances the flow."""
    nxt = next_step(current)
    if not nxt:
        return
    if st.button(label or f"Next: {nxt} →", type=kind, key=key or f"next_{current}"):
        goto(nxt)
