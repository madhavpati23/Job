"""Step 5 — a log of what you applied to.

The app deliberately stores nothing server-side, so a browser refresh ends the
Streamlit session and takes the in-memory log with it. Rather than break that
promise, the log round-trips through a CSV the user holds: export to keep it,
re-import to carry it into the next session.
"""

from __future__ import annotations

import csv
import io
from datetime import date

import streamlit as st

FIELDS = ["date", "company", "role", "location", "url", "status"]
STATUSES = ["applied", "screening", "interviewing", "offer", "rejected", "withdrawn"]


def add(company: str, role: str, location: str = "", url: str = "") -> None:
    """Append an application, stamped with today's date."""
    st.session_state.setdefault("applications", []).append(
        {
            "date": date.today().isoformat(),
            "company": company,
            "role": role,
            "location": location,
            "url": url,
            "status": "applied",
        }
    )


def _normalize(row: dict) -> dict:
    return {
        # Preserve the original date on import; only default when truly absent.
        "date": (row.get("date") or "").strip() or date.today().isoformat(),
        "company": (row.get("company") or "").strip(),
        "role": (row.get("role") or "").strip(),
        "location": (row.get("location") or "").strip(),
        "url": (row.get("url") or "").strip(),
        "status": (row.get("status") or "applied").strip() or "applied",
    }


def _to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _import_csv(uploaded) -> tuple[int, int]:
    """Merge an exported CSV back in. Returns (added, skipped_duplicates)."""
    text = uploaded.read().decode("utf-8-sig", errors="replace")
    rows = [_normalize(r) for r in csv.DictReader(io.StringIO(text))]
    rows = [r for r in rows if r["company"] or r["role"]]

    existing = st.session_state.setdefault("applications", [])
    seen = {(r.get("company", ""), r.get("role", ""), r.get("date", "")) for r in existing}

    added = 0
    for row in rows:
        signature = (row["company"], row["role"], row["date"])
        if signature in seen:
            continue
        seen.add(signature)
        existing.append(row)
        added += 1
    return added, len(rows) - added


def render() -> None:
    st.header("5 · Application tracker")

    apps = st.session_state.setdefault("applications", [])
    rows = [_normalize(a) for a in apps]

    st.caption(
        "Nothing is stored on the server, so a refresh clears this. "
        "**Download the CSV to keep it, and re-upload it next visit to carry it forward.**"
    )

    with st.expander("Restore a previous tracker (upload CSV)"):
        uploaded = st.file_uploader(
            "applications.csv", type=["csv"], key="tracker_csv",
            help="Upload a CSV exported from this app. Duplicates are skipped.",
        )
        if uploaded is not None and st.button("Import"):
            try:
                added, skipped = _import_csv(uploaded)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Couldn't read that CSV: {exc}")
            else:
                msg = f"Imported {added} application(s)."
                if skipped:
                    msg += f" Skipped {skipped} already in the list."
                st.success(msg)
                st.rerun()

    with st.form("add_application", clear_on_submit=True):
        col1, col2 = st.columns(2)
        company = col1.text_input("Company")
        role = col2.text_input("Role")
        col3, col4 = st.columns(2)
        location = col3.text_input("Location")
        url = col4.text_input("Posting URL")
        if st.form_submit_button("Add row") and (company or role):
            add(company, role, location, url)
            st.rerun()

    if not rows:
        st.info(
            "Nothing logged yet. Add a row above, use **Log this as applied** on the "
            "cover letter page, or import a CSV from a previous session."
        )
        return

    # Editable so status can move on (applied -> interviewing -> offer) without
    # re-typing the row.
    edited = st.data_editor(
        rows,
        width="stretch",
        num_rows="dynamic",
        key="tracker_editor",
        column_config={
            "status": st.column_config.SelectboxColumn("status", options=STATUSES),
            "url": st.column_config.LinkColumn("url"),
        },
    )
    if edited != rows:
        st.session_state.applications = [_normalize(r) for r in edited]

    col1, col2 = st.columns(2)
    col1.download_button(
        "Download CSV", _to_csv(st.session_state.applications),
        file_name="applications.csv", mime="text/csv", type="primary",
    )
    if col2.button("Clear all"):
        st.session_state.applications = []
        st.rerun()
