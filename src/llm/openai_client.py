"""LLM client wrapper with a process-local call counter (G9 invariant).

Two providers are supported by environment configuration:

- **OpenAI direct** (default): set ``OPENAI_API_KEY`` to ``sk-...``; leave
  ``OPENAI_BASE_URL`` unset.
- **OpenRouter** (cheaper chat): set ``OPENAI_API_KEY`` to ``sk-or-...`` and
  ``OPENAI_BASE_URL=https://openrouter.ai/api/v1``. ``OPENAI_CHAT_MODEL``
  becomes an OpenRouter model id (e.g. ``openai/gpt-4o-mini``,
  ``anthropic/claude-3.5-sonnet``). OpenRouter does **not** serve embeddings,
  so embeddings always go to OpenAI proper using
  ``OPENAI_EMBEDDING_API_KEY`` (falls back to ``OPENAI_API_KEY`` only if
  ``OPENAI_BASE_URL`` is unset).

In ``USE_MOCK_LLM=true`` mode, both ``embed`` and ``chat`` route to
``src.llm.mock`` and the counter is NOT incremented (mock calls are free
and do not violate the "replay must make zero LLM calls" assertion).
"""
from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from src.config import settings
from src.llm import mock as _mock

log = logging.getLogger(__name__)

_call_counter = 0
_lock = Lock()


def reset_counter() -> None:
    global _call_counter
    with _lock:
        _call_counter = 0


def call_counter() -> int:
    return _call_counter


def _bump() -> None:
    global _call_counter
    with _lock:
        _call_counter += 1


def _chat_client():  # lazy import; only used when not in mock mode
    from openai import OpenAI
    kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**kwargs)


def _embedding_client():
    from openai import OpenAI
    # If chat is going through OpenRouter, embeddings still need OpenAI proper.
    using_proxy = bool(settings.openai_base_url)
    api_key = (
        settings.openai_embedding_api_key
        if using_proxy and settings.openai_embedding_api_key
        else settings.openai_api_key
    )
    if using_proxy and not settings.openai_embedding_api_key:
        log.warning(
            "OPENAI_BASE_URL is set (chat via proxy) but OPENAI_EMBEDDING_API_KEY "
            "is not — embeddings will reuse OPENAI_API_KEY against api.openai.com, "
            "which will fail if that key is an OpenRouter key."
        )
    return OpenAI(api_key=api_key)  # no base_url => api.openai.com


def embed(text: str) -> list[float]:
    if settings.use_mock_llm:
        return _mock.embed(text)
    _bump()
    resp = _embedding_client().embeddings.create(
        model=settings.openai_embedding_model, input=text
    )
    return resp.data[0].embedding


def chat(prompt: str, role: str = "agent", **kwargs: Any) -> str:
    if settings.use_mock_llm:
        return _mock.chat(prompt, role=role, **kwargs)
    _bump()
    resp = _chat_client().chat.completions.create(
        model=settings.openai_chat_model,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content or ""
