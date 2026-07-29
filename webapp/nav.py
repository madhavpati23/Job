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


def next_step(current: str) -> str | None:
    idx = STEPS.index(current)
    return STEPS[idx + 1] if idx + 1 < len(STEPS) else None


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
