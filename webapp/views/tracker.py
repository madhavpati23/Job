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

from webapp import store

FIELDS = ["date", "company", "role", "location", "url", "status"]
STATUSES = ["applied", "screening", "interviewing", "offer", "rejected", "withdrawn"]


def _autosave() -> None:
    """Persist immediately when a token is active, so edits aren't lost."""
    token = st.session_state.get("tracker_token", "")
    if token and store.enabled():
        try:
            store.save(token, st.session_state.get("applications", []))
        except Exception:  # noqa: BLE001 — saving is best-effort, never fatal
            pass


def add(company: str, role: str, location: str = "", url: str = "") -> None:
    """Append an application, stamped with today's date, and persist it."""
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
    # Without this, an application logged from the cover-letter page stayed in
    # memory only and vanished on refresh even with server saving switched on.
    _autosave()


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
    # Rewind: Streamlit reuses the upload object across reruns, so a second
    # Import click would otherwise read an exhausted stream and import nothing.
    if hasattr(uploaded, "seek"):
        try:
            uploaded.seek(0)
        except (OSError, ValueError):
            pass
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


def _sync_from_url() -> None:
    """Adopt a tracker token from the URL once per session, and load its rows."""
    if st.session_state.get("_tracker_loaded"):
        return
    token = st.query_params.get(store.TOKEN_PARAM, "")
    if token:
        rows, updated = store.load(token)
        st.session_state.tracker_token = token
        if rows:
            st.session_state.applications = rows
            st.session_state.tracker_loaded_at = updated
    st.session_state._tracker_loaded = True


def _server_storage(rows: list[dict]) -> None:
    """Opt-in save/restore panel. Only shown when the deployment allows it."""
    token = st.session_state.get("tracker_token", "")

    with st.expander("Save on the server", expanded=bool(token)):
        note = store.warning()
        if note:
            st.warning(note)

        if token:
            st.success("This tracker is saved. Bookmark the URL to come back to it.")
            st.code(f"?{store.TOKEN_PARAM}={token}", language="text")
            loaded = st.session_state.get("tracker_loaded_at")
            if loaded:
                st.caption(f"Last saved {loaded} UTC.")
            st.caption(
                "Anyone with this link can read and change the tracker — it's the "
                "only credential. Don't share it."
            )
            col1, col2 = st.columns(2)
            if col1.button("Save now", type="primary"):
                store.save(token, rows)
                st.success("Saved.")
            if col2.button("Stop saving & delete from server"):
                store.delete(token)
                st.session_state.pop("tracker_token", None)
                st.query_params.pop(store.TOKEN_PARAM, None)
                st.rerun()
        else:
            st.caption(
                "Creates a private link that stores this tracker so it survives a "
                "refresh. No account, no email — the link is the only key."
            )
            if st.button("Enable server saving", type="primary"):
                new = store.new_token()
                store.save(new, rows)
                st.session_state.tracker_token = new
                st.query_params[store.TOKEN_PARAM] = new
                st.rerun()

            existing = st.text_input(
                "Or restore an existing tracker link", placeholder="paste the token",
                key="tracker_token_input",
            )
            if existing.strip() and st.button("Restore"):
                loaded_rows, updated = store.load(existing.strip())
                if not loaded_rows:
                    st.error("No tracker found for that token.")
                else:
                    st.session_state.applications = loaded_rows
                    st.session_state.tracker_token = existing.strip()
                    st.session_state.tracker_loaded_at = updated
                    st.query_params[store.TOKEN_PARAM] = existing.strip()
                    st.rerun()


def render() -> None:
    st.header("5 · Application tracker")

    if store.enabled():
        _sync_from_url()

    apps = st.session_state.setdefault("applications", [])
    rows = [_normalize(a) for a in apps]

    if store.enabled():
        _server_storage(rows)
        st.caption(
            "Not saving on the server? **Download the CSV** and re-upload it next visit."
        )
    else:
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
        _autosave()

    col1, col2 = st.columns(2)
    col1.download_button(
        "Download CSV", _to_csv(st.session_state.applications),
        file_name="applications.csv", mime="text/csv", type="primary",
    )
    if col2.button("Clear all"):
        st.session_state.applications = []
        st.rerun()
