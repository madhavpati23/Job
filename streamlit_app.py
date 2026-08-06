"""Job Copilot — upload a resume, find matching jobs, tailor, and write cover letters.

Run locally:   streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from webapp import aihint, llm, nav, providers
from webapp.views import jobs, letter, resume, tracker, tailor

st.set_page_config(page_title="Job Copilot", page_icon="🎯", layout="wide")

PAGES = {
    "Resume": resume.render,
    "Find jobs": jobs.render,
    "Tailor resume": tailor.render,
    "Cover letter": letter.render,
    "Tracker": tracker.render,
}


def ai_settings(auto_expand: bool = False) -> None:
    """Provider / model / key picker. Only steps 3 and 4 need it."""
    st.sidebar.subheader("AI provider")
    st.sidebar.caption(
        "Powers **3 · Tailor resume** and **4 · Cover letter**. "
        "Steps 1, 2, and 5 work without it."
    )

    with st.sidebar.expander("Set up AI writing", expanded=auto_expand):
        ids = list(providers.PROVIDERS)
        pid = st.selectbox(
            "Provider",
            ids,
            index=ids.index(st.session_state.get("llm_provider", providers.DEFAULT_PROVIDER)),
            format_func=lambda i: providers.PROVIDERS[i].label,
            key="llm_provider",
        )
        provider = providers.get(pid)

        # Model lists are per-provider; keeping the previous provider's list
        # would offer models the new one has never heard of.
        if st.session_state.get("_llm_provider_seen") != pid:
            st.session_state["_llm_provider_seen"] = pid
            st.session_state.pop("llm_model_options", None)
            st.session_state.pop("llm_model", None)

        if not providers.installed(provider):
            st.warning(f"`pip install {provider.package}` to use {provider.label}.")

        if provider.needs_base_url:
            st.text_input(
                "Base URL", key="llm_base_url",
                placeholder="https://openrouter.ai/api/v1",
                help=providers.OPENAI_COMPATIBLE_HINT,
            )
        elif provider.base_url:
            st.caption(f"Endpoint: `{provider.base_url}`")

        env_key = providers.resolve_key(provider)
        if env_key:
            st.success(f"Key found in secrets/environment (`{provider.env_var}`).")
        else:
            st.text_input(
                f"{provider.label} API key", type="password",
                placeholder=provider.key_hint, key="llm_key",
                help="Used for this session only — never stored or logged.",
            )
            if provider.console_url:
                st.caption(f"Get a key: {provider.console_url}")

        # Model IDs change often, so ask the provider rather than hardcoding a
        # list that silently goes stale.
        key = providers.resolve_key(provider, st.session_state.get("llm_key", ""))
        base_url = st.session_state.get("llm_base_url", "")
        if key or base_url:
            if st.button("Load available models", key="load_models"):
                try:
                    st.session_state.llm_model_options = providers.list_models(
                        provider, key, base_url
                    )
                except providers.ProviderError as exc:
                    st.session_state.llm_model_options = []
                    st.error(str(exc))

            options = st.session_state.get("llm_model_options") or []
            if options:
                default = provider.default_model
                idx = options.index(default) if default in options else 0
                st.selectbox("Model", options, index=idx, key="llm_model")
            else:
                st.text_input(
                    "Model", value=st.session_state.get("llm_model", provider.default_model),
                    key="llm_model",
                    help="Type a model ID, or click Load available models.",
                )

    st.sidebar.caption(aihint.status_line())


def sidebar() -> str:
    # Must run before the radio below is instantiated — see webapp/nav.py.
    nav.apply_pending()

    st.sidebar.title("🎯 Job Copilot")

    # The step list carries the status: ✅ done, 🔒 blocked, ○ available. That
    # replaces a separate Status block that repeated the same facts.
    states = nav.progress()
    choice = st.sidebar.radio(
        "Steps", list(PAGES), key=nav.NAV_KEY,
        format_func=lambda s: nav.step_label(s, states),
        label_visibility="collapsed",
    )

    selected = st.session_state.get("selected_job")
    if selected:
        st.sidebar.caption(f"Job: **{selected['company']}** — {selected['title'].strip()[:40]}")

    st.sidebar.divider()
    # Open the panel automatically when the step the user is on requires it —
    # a collapsed control they've never noticed isn't discoverable.
    ai_settings(auto_expand=choice in aihint.AI_STEPS and not llm.available())

    st.sidebar.divider()
    st.sidebar.caption(
        "Job data comes from public APIs (Greenhouse, Lever, Ashby, Remotive, "
        "The Muse, SmartRecruiters, Adzuna). Nothing you upload is stored server-side."
    )
    return choice


def main() -> None:
    choice = sidebar()
    PAGES[choice]()


if __name__ == "__main__":
    main()
