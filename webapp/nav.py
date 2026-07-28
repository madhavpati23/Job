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


def next_step(current: str) -> str | None:
    idx = STEPS.index(current)
    return STEPS[idx + 1] if idx + 1 < len(STEPS) else None


def next_button(
    current: str,
    label: str | None = None,
    key: str | None = None,
    type: str = "primary",
) -> None:
    """Render a 'Next: <step>' button that advances the flow."""
    nxt = next_step(current)
    if not nxt:
        return
    if st.button(label or f"Next: {nxt} →", type=type, key=key or f"next_{current}"):
        goto(nxt)
