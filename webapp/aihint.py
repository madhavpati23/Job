"""Shared UI for the AI-provider prerequisite on steps 3 and 4.

Both AI steps previously failed quietly: a one-line info box mentioned "the
sidebar" while the sidebar control sat collapsed and unlabelled, so there was
nothing connecting the two. This renders the setup state prominently on the
page itself, and the sidebar auto-expands when a step actually needs it.

The controls themselves stay in the sidebar — Streamlit keys must be unique
per run, so the picker can't be drawn in both places at once.
"""

from __future__ import annotations

import streamlit as st

from webapp import llm, providers

AI_STEPS = ("Tailor resume", "Cover letter")


def needs_setup() -> bool:
    """True when the current page needs an AI provider and none is usable."""
    return not llm.available()


def status_line() -> str:
    """One-line summary for the sidebar."""
    if llm.available():
        cfg = llm.settings()
        return f"AI writing: ✅ {cfg['provider'].label} · `{cfg['model']}`"
    return "AI writing: ⚠️ not set up — needed for steps 3 and 4"


def setup_callout(what: str) -> None:
    """Explain what's missing and exactly how to fix it, on the page."""
    st.warning(f"**An AI provider is required to {what}.**")

    with st.container(border=True):
        st.markdown(
            "#### Set this up in the sidebar\n"
            "The **Set up AI writing** panel on the left is now open. Three steps:\n\n"
            "1. **Pick a provider** — Anthropic, OpenAI, Google, Groq, or any "
            "OpenAI-compatible endpoint\n"
            "2. **Paste your API key** — used for this session only, never stored\n"
            "3. **Load available models** and pick one\n"
        )
        names = ", ".join(p.label for p in providers.PROVIDERS.values())
        st.caption(f"Supported: {names}.")
        st.caption(
            "Bring a key from a provider you already use. Groq has a free tier; "
            "Ollama and LM Studio run locally with no key at all."
        )

    st.info(
        "**Everything else works without a key** — job search, resume matching, "
        "the keyword gap analysis, and the cover-letter scaffold."
    )


def ready_badge() -> None:
    """Compact confirmation of which model will be used."""
    cfg = llm.settings()
    st.caption(f"✅ Using **{cfg['provider'].label}** · `{cfg['model']}` — change it in the sidebar.")
