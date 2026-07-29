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
