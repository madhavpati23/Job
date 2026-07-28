"""Job Copilot — upload a resume, find matching jobs, tailor, and write cover letters.

Run locally:   streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from webapp import llm, nav, providers
from webapp.views import jobs, letter, resume, tracker, tailor

st.set_page_config(page_title="Job Copilot", page_icon="🎯", layout="wide")

PAGES = {
    "Resume": resume.render,
    "Find jobs": jobs.render,
    "Tailor resume": tailor.render,
    "Cover letter": letter.render,
    "Tracker": tracker.render,
}


def ai_settings() -> None:
    """Provider / model / key picker. Optional — only the AI writing needs it."""
    st.sidebar.subheader("AI provider *(optional)*")
    st.sidebar.caption(
        "**Job search, matching, and the cover-letter scaffold work without this.** "
        "Add a provider only to generate a rewritten resume or a finished letter."
    )

    with st.sidebar.expander("Set up AI writing", expanded=False):
        ids = list(providers.PROVIDERS)
        pid = st.selectbox(
            "Provider",
            ids,
            index=ids.index(st.session_state.get("llm_provider", providers.DEFAULT_PROVIDER)),
            format_func=lambda i: providers.PROVIDERS[i].label,
            key="llm_provider",
        )
        provider = providers.get(pid)

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

    if llm.available():
        cfg = llm.settings()
        st.sidebar.caption(f"AI writing: ✅ {cfg['provider'].label} · `{cfg['model']}`")


def sidebar() -> str:
    # Must run before the radio below is instantiated — see webapp/nav.py.
    nav.apply_pending()

    st.sidebar.title("🎯 Job Copilot")
    choice = st.sidebar.radio(
        "Steps", list(PAGES), key=nav.NAV_KEY, label_visibility="collapsed"
    )

    st.sidebar.divider()
    st.sidebar.subheader("Status")
    resume_text = st.session_state.get("resume_text", "")
    st.sidebar.write(
        f"Resume: {'✅ ' + st.session_state.get('resume_name', 'loaded') if resume_text else '— none'}"
    )
    selected = st.session_state.get("selected_job")
    st.sidebar.write(
        f"Job: {'✅ ' + selected['company'] if selected else '— none selected'}"
    )

    st.sidebar.divider()
    ai_settings()

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
