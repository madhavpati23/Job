"""Step 5 — a session-scoped log of what you applied to."""

from __future__ import annotations

import csv
import io
from datetime import date

import streamlit as st

FIELDS = ["date", "company", "role", "location", "url", "status"]


def render() -> None:
    st.header("5 · Application tracker")
    st.caption(
        "Scoped to this browser session — download the CSV to keep it. "
        "Closing the tab clears it."
    )

    apps = st.session_state.setdefault("applications", [])

    with st.form("add_application", clear_on_submit=True):
        col1, col2 = st.columns(2)
        company = col1.text_input("Company")
        role = col2.text_input("Role")
        col3, col4 = st.columns(2)
        location = col3.text_input("Location")
        url = col4.text_input("Posting URL")
        if st.form_submit_button("Add row") and (company or role):
            apps.append({"company": company, "role": role, "location": location, "url": url})

    if not apps:
        st.info("Nothing logged yet. Add a row above, or use **Log this as applied** on the cover letter page.")
        return

    rows = [
        {
            "date": a.get("date") or date.today().isoformat(),
            "company": a.get("company", ""),
            "role": a.get("role", ""),
            "location": a.get("location", ""),
            "url": a.get("url", ""),
            "status": a.get("status", "applied"),
        }
        for a in apps
    ]
    st.dataframe(rows, use_container_width=True)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)

    col1, col2 = st.columns(2)
    col1.download_button(
        "Download CSV", buf.getvalue(), file_name="applications.csv", mime="text/csv"
    )
    if col2.button("Clear all"):
        st.session_state.applications = []
        st.rerun()
