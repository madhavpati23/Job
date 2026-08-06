"""Optional per-machine storage for the LLM API key.

The app's default is that a key is used for the session and forgotten. This
module is the opt-in exception, and it is deliberately narrow:

  * The key goes into the operating system's credential vault — Windows
    Credential Manager, macOS Keychain, or Secret Service on Linux — never into
    a file we write, the tracker database, or the URL. The OS encrypts it at
    rest under the logged-in user account, so another account on the same
    machine cannot read it.
  * Saving is offered only when the app looks like it is running locally. On a
    shared deployment one visitor's key would otherwise be handed to the next,
    so there the option hides itself and `st.secrets` remains the way in.
  * Backends that only pretend to store secrets are rejected. keyring falls back
    to a plaintext file backend when no vault is present, which would quietly
    turn "saved securely" into a readable file on disk.

Nothing here is required: with no keyring installed the app behaves exactly as
it did before, asking for the key each session.
"""

from __future__ import annotations

import os
from pathlib import Path

SERVICE = "jobapply-webapp"

# keyring picks a backend at import time. These two store nothing and store
# plaintext respectively, and either would make the "encrypted at rest" promise
# false, so both are treated as "no vault available".
_REJECTED = ("fail", "plaintext", "null")


def _keyring():
    try:
        import keyring
    except Exception:
        return None
    return keyring


def backend_name() -> str:
    """Human-readable vault name, or '' when there isn't a usable one."""
    kr = _keyring()
    if kr is None:
        return ""
    try:
        backend = kr.get_keyring()
    except Exception:
        return ""
    cls = type(backend)
    dotted = f"{cls.__module__}.{cls.__name__}".lower()
    if any(bad in dotted for bad in _REJECTED):
        return ""
    return {
        "winvaultkeyring": "Windows Credential Manager",
        "keyring": "macOS Keychain",
        "secretservice": "Secret Service (GNOME Keyring)",
        "kwallet": "KDE Wallet",
    }.get(cls.__name__.lower(), cls.__name__)


def shared_deployment() -> bool:
    """True when this looks like a server other people can reach.

    Errs toward 'shared': a wrong 'local' guess would offer to persist a key on
    a box strangers use, while a wrong 'shared' guess only costs the user a
    checkbox they can replace with secrets.toml.
    """
    if os.environ.get("JOBAPPLY_SHARED", "").lower() in ("1", "true", "yes", "on"):
        return True
    if os.environ.get("JOBAPPLY_LOCAL", "").lower() in ("1", "true", "yes", "on"):
        return False
    # Streamlit Community Cloud checks out the repo under /mount/src and sets
    # its own hostname; neither exists on a laptop.
    if Path("/mount/src").exists():
        return True
    if os.environ.get("STREAMLIT_SHARING_MODE") or os.environ.get("STREAMLIT_SERVER_HEADLESS") == "true":
        return True
    return False


def available() -> bool:
    """Can we offer to remember a key right now?"""
    return bool(backend_name()) and not shared_deployment()


def _entry(provider_id: str) -> str:
    return f"llm_key:{provider_id}"


def load(provider_id: str) -> str:
    if not available():
        return ""
    kr = _keyring()
    try:
        return kr.get_password(SERVICE, _entry(provider_id)) or ""
    except Exception:
        return ""


def save(provider_id: str, key: str) -> bool:
    if not available() or not key:
        return False
    kr = _keyring()
    try:
        kr.set_password(SERVICE, _entry(provider_id), key)
        return True
    except Exception:
        return False


def delete(provider_id: str) -> bool:
    """Remove a stored key. Absent is success — the caller wanted it gone."""
    if not backend_name():
        return False
    kr = _keyring()
    try:
        kr.delete_password(SERVICE, _entry(provider_id))
        return True
    except Exception:
        return not load(provider_id)


def has_saved(provider_id: str) -> bool:
    return bool(load(provider_id))
