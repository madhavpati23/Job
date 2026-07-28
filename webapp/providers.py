"""Pluggable LLM backends for resume tailoring and cover letters.

Users bring whichever provider they already pay for. Each backend exposes the
same two operations — list the models this key can reach, and complete a
system+user prompt — so the rest of the app never branches on provider.

Model IDs are fetched from each provider's own API rather than hardcoded: a
baked-in list goes stale every few months and silently breaks the app.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

# An OpenAI-compatible endpoint covers a large slice of the ecosystem with one
# client: Groq, Together, OpenRouter, DeepSeek, Mistral, Fireworks, vLLM,
# Ollama, LM Studio, and Azure OpenAI all speak this protocol.
OPENAI_COMPATIBLE_HINT = (
    "Any OpenAI-compatible endpoint — Groq, Together, OpenRouter, DeepSeek, "
    "Fireworks, vLLM, Ollama (http://localhost:11434/v1), LM Studio."
)


class ProviderError(RuntimeError):
    """Anything the user can act on: missing package, bad key, refusal.

    `detail` carries the provider's raw text so the UI can offer it on demand
    without putting a JSON dump in front of the user.
    """

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


def _friendly(exc: Exception, provider: "Provider", model: str) -> ProviderError:
    """Turn a provider SDK exception into something the user can act on.

    Providers raise wildly different exception types with multi-line JSON in
    str(exc), so this matches on the text rather than the class.
    """
    raw = str(exc)
    low = raw.lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)

    quota_zero = "limit: 0" in low or "limit:0" in low
    if quota_zero:
        msg = (
            f"**{model}** isn't available on your {provider.label} plan — the account "
            f"shows a quota of zero for it, so every request is rejected. Pick a "
            f"different model in the sidebar (**Load available models**), or enable "
            f"billing with {provider.label}."
        )
    elif status == 429 or "429" in low or "resource_exhausted" in low or "rate limit" in low or "quota" in low:
        msg = (
            f"{provider.label} rate limit or quota reached. Wait a moment and retry, "
            f"pick a smaller/cheaper model, or check your plan's billing settings."
        )
    elif status in (401, 403) or "api key" in low or "unauthorized" in low or \
            "permission_denied" in low or "authentication" in low or "invalid_api_key" in low:
        msg = (
            f"{provider.label} rejected the API key. Check it's correct, active, and "
            f"has access to {model}."
        )
    elif status == 404 or "not found" in low or "does not exist" in low or "not_found" in low:
        msg = (
            f"**{model}** wasn't found on {provider.label}. Click **Load available "
            f"models** in the sidebar and pick one from the list."
        )
    elif "context" in low and ("length" in low or "window" in low or "too long" in low):
        msg = (
            "The resume and job description together exceed this model's context "
            "window. Try a model with a larger context, or shorten the posting."
        )
    elif "connection" in low or "timeout" in low or "timed out" in low:
        msg = (
            f"Couldn't reach {provider.label}. Check your network — some corporate "
            f"networks block AI provider domains."
        )
    else:
        msg = f"{provider.label} returned an error."

    return ProviderError(msg, detail=raw)


@dataclass
class Provider:
    key_id: str                     # internal id
    label: str                      # shown in the UI
    package: str                    # pip package that must be importable
    env_var: str                    # env / secrets name for the key
    key_hint: str                   # placeholder text
    default_model: str              # used if model listing fails
    needs_base_url: bool = False    # ask the user for one
    base_url: str = ""              # fixed endpoint for OpenAI-compatible hosts
    console_url: str = ""
    list_models: Callable[..., list[str]] = field(repr=False, default=None)
    complete: Callable[..., str] = field(repr=False, default=None)


# --- Anthropic ------------------------------------------------------------

def _anthropic_models(key: str, base_url: str = "") -> list[str]:
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    return [m.id for m in client.models.list()]


def _anthropic_complete(system: str, prompt: str, key: str, model: str,
                        max_tokens: int, base_url: str = "") -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    # Server-side fallbacks re-route if a safety classifier declines, so a
    # borderline posting can't dead-end the user. Older SDKs lack the param.
    try:
        with client.beta.messages.stream(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
        ) as stream:
            message = stream.get_final_message()
    except (TypeError, AttributeError, anthropic.BadRequestError):
        with client.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise ProviderError("The model declined this request. Try a different posting.")
    return "".join(b.text for b in message.content if b.type == "text").strip()


# --- OpenAI and OpenAI-compatible ----------------------------------------

_NON_CHAT = ("embedding", "whisper", "tts", "dall-e", "moderation", "audio",
             "image", "realtime", "transcribe", "search", "similarity", "edit")


def _openai_client(key: str, base_url: str = ""):
    import openai

    return openai.OpenAI(api_key=key or "not-needed", base_url=base_url or None)


def _openai_models(key: str, base_url: str = "") -> list[str]:
    client = _openai_client(key, base_url)
    ids = [m.id for m in client.models.list().data]
    chat = [i for i in ids if not any(x in i.lower() for x in _NON_CHAT)]
    return sorted(chat or ids)


def _openai_complete(system: str, prompt: str, key: str, model: str,
                     max_tokens: int, base_url: str = "") -> str:
    client = _openai_client(key, base_url)
    # max_tokens is deliberately omitted: providers disagree on the parameter
    # name (max_tokens vs max_completion_tokens) and some reject the wrong one,
    # so letting the server default is the portable choice.
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


# --- Google Gemini --------------------------------------------------------

def _google_models(key: str, base_url: str = "") -> list[str]:
    from google import genai

    client = genai.Client(api_key=key)
    out = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if not actions or "generateContent" in actions:
            out.append(str(m.name).removeprefix("models/"))
    return sorted(out)


def _google_complete(system: str, prompt: str, key: str, model: str,
                     max_tokens: int, base_url: str = "") -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return (resp.text or "").strip()


PROVIDERS: dict[str, Provider] = {
    "anthropic": Provider(
        key_id="anthropic", label="Anthropic (Claude)", package="anthropic",
        env_var="ANTHROPIC_API_KEY", key_hint="sk-ant-…",
        default_model="claude-opus-5", console_url="https://console.anthropic.com",
        list_models=_anthropic_models, complete=_anthropic_complete,
    ),
    "openai": Provider(
        key_id="openai", label="OpenAI", package="openai",
        env_var="OPENAI_API_KEY", key_hint="sk-…",
        default_model="gpt-4o", console_url="https://platform.openai.com/api-keys",
        list_models=_openai_models, complete=_openai_complete,
    ),
    "google": Provider(
        key_id="google", label="Google (Gemini)", package="google-genai",
        env_var="GOOGLE_API_KEY", key_hint="AIza…",
        default_model="gemini-2.0-flash", console_url="https://aistudio.google.com/apikey",
        list_models=_google_models, complete=_google_complete,
    ),
    "groq": Provider(
        key_id="groq", label="Groq", package="openai",
        env_var="GROQ_API_KEY", key_hint="gsk_…",
        default_model="llama-3.3-70b-versatile",
        base_url="https://api.groq.com/openai/v1",
        console_url="https://console.groq.com/keys",
        list_models=_openai_models, complete=_openai_complete,
    ),
    "custom": Provider(
        key_id="custom", label="Other (OpenAI-compatible)", package="openai",
        env_var="LLM_API_KEY", key_hint="your API key",
        default_model="", needs_base_url=True,
        list_models=_openai_models, complete=_openai_complete,
    ),
}

DEFAULT_PROVIDER = "anthropic"


def get(provider_id: str) -> Provider:
    return PROVIDERS.get(provider_id) or PROVIDERS[DEFAULT_PROVIDER]


def installed(provider: Provider) -> bool:
    import importlib.util

    module = {"google-genai": "google.genai"}.get(provider.package, provider.package)
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def resolve_key(provider: Provider, user_key: str = "") -> str:
    """User input first, then Streamlit secrets, then the environment."""
    if user_key.strip():
        return user_key.strip()
    try:
        import streamlit as st

        if provider.env_var in st.secrets:
            return str(st.secrets[provider.env_var])
    except Exception:
        pass
    return os.environ.get(provider.env_var, "")


def effective_base_url(provider: Provider, user_base_url: str = "") -> str:
    """A provider's fixed endpoint wins; otherwise whatever the user typed."""
    return provider.base_url or user_base_url


def list_models(provider: Provider, key: str, base_url: str = "") -> list[str]:
    if not installed(provider):
        raise ProviderError(f"`pip install {provider.package}` to use {provider.label}.")
    try:
        return provider.list_models(key, effective_base_url(provider, base_url))
    except Exception as exc:  # noqa: BLE001
        raise _friendly(exc, provider, "the model list") from exc


def complete(provider: Provider, system: str, prompt: str, key: str,
             model: str, max_tokens: int = 20000, base_url: str = "") -> str:
    if not installed(provider):
        raise ProviderError(f"`pip install {provider.package}` to use {provider.label}.")
    if not key and not base_url:
        raise ProviderError(f"No API key set for {provider.label}.")
    chosen = model or provider.default_model
    try:
        text = provider.complete(system, prompt, key, chosen, max_tokens,
                                 effective_base_url(provider, base_url))
    except ProviderError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _friendly(exc, provider, chosen) from exc
    if not text:
        raise ProviderError("The model returned an empty response — try again.")
    return text
