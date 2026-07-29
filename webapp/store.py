"""Optional server-side persistence for the application tracker.

The app's default promise is that nothing is kept server-side. Saving the
tracker breaks that for the one user who asks for it, so this is strictly
opt-in and scoped by a random token the user holds:

  * A token is a 22-char secret. Rows are stored under it and readable only by
    presenting it. There are no accounts and no email — losing the token means
    losing the data, which is the point: we hold nothing that identifies anyone.
  * The token rides in the URL (?t=…), so a refresh keeps the session.

Storage is SQLite on local disk. On Streamlit Community Cloud that disk is
ephemeral — it is wiped on redeploy and when the app sleeps — so `warning()`
tells the user when saves won't be durable. Point TRACKER_DB at a mounted
volume, or run locally, for persistence you can rely on.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "tracker.db"
TOKEN_PARAM = "t"


def db_path() -> Path:
    return Path(os.environ.get("TRACKER_DB") or DEFAULT_DB)


def enabled() -> bool:
    """Server-side saving is off unless explicitly switched on."""
    if os.environ.get("TRACKER_STORAGE", "").lower() in ("1", "true", "yes", "on"):
        return True
    try:
        import streamlit as st

        return str(st.secrets.get("TRACKER_STORAGE", "")).lower() in ("1", "true", "yes", "on")
    except Exception:
        return False


def durable() -> bool:
    """False when the database sits on disk we know to be ephemeral."""
    return bool(os.environ.get("TRACKER_DB"))


def warning() -> str:
    if durable():
        return ""
    return (
        "Saved data lives on the app server's local disk. On Streamlit Community "
        "Cloud that disk is wiped on redeploy and when the app sleeps, so treat "
        "this as convenience, not backup — keep downloading the CSV."
    )


@contextmanager
def _connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS trackers ("
            " token TEXT PRIMARY KEY,"
            " rows TEXT NOT NULL,"
            " updated_at TEXT NOT NULL)"
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def new_token() -> str:
    return secrets.token_urlsafe(16)


def save(token: str, rows: list[dict]) -> None:
    if not token:
        raise ValueError("a token is required")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO trackers (token, rows, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(token) DO UPDATE SET rows=excluded.rows, updated_at=excluded.updated_at",
            (token, json.dumps(rows), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )


def load(token: str) -> tuple[list[dict], str | None]:
    """Return (rows, updated_at). Missing or malformed tokens give ([], None)."""
    if not token:
        return [], None
    with _connect() as conn:
        row = conn.execute(
            "SELECT rows, updated_at FROM trackers WHERE token = ?", (token,)
        ).fetchone()
    if not row:
        return [], None
    try:
        return json.loads(row[0]), row[1]
    except (json.JSONDecodeError, TypeError):
        return [], row[1]


def delete(token: str) -> None:
    if not token:
        return
    with _connect() as conn:
        conn.execute("DELETE FROM trackers WHERE token = ?", (token,))
