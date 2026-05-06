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

from src.core.config import settings
from src.llm import mock as _mock
from src.llm import replay as _replay

log = logging.getLogger(__name__)

_call_counter = 0
_lock = Lock()
# Process-local cache of embeddings keyed on (model, text). Embedding the
# same string twice in a single run is wasteful and is a common pattern
# (e.g. coalition formation embeds each capability and search_skills
# embeds the same string a moment later). Cache hits do not bump the
# call counter, keeping G9 honest.
_embed_cache: dict[tuple[str, str], list[float]] = {}


def reset_counter() -> None:
    """Reset the process-local LLM call counter to 0 (used by replay)."""
    global _call_counter
    with _lock:
        _call_counter = 0
        _embed_cache.clear()


def call_counter() -> int:
    """Return the current LLM call count (G9 replay invariant)."""
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
    """Return an embedding for ``text`` (mocked when ``USE_MOCK_LLM=true``).

    Real-mode results are cached per-process on (model, text) so the same
    string is only embedded once. When ``settings.use_llm_cache=True`` an
    additional MongoDB-backed cache (`llm_cache` collection) survives
    across processes and runs; cache hits do **not** bump the call
    counter.
    """
    if settings.use_mock_llm:
        # Demo / publish path: prefer captured real responses from
        # data/llm_replay_cache.json so the curated prompts look like
        # they did during the hackathon. Unknown payloads fall through
        # to deterministic stubs in src/llm/mock.py.
        cached = _replay.lookup("embed", text)
        if cached is not None:
            return cached
        return _mock.embed(text)
    key = (settings.openai_embedding_model, text)
    cached = _embed_cache.get(key)
    if cached is not None:
        return cached
    # Persistent cache hit?
    persisted = _cache_get("embed", settings.openai_embedding_model, text)
    if persisted is not None:
        _embed_cache[key] = persisted
        return persisted
    _bump()
    resp = _embedding_client().embeddings.create(
        model=settings.openai_embedding_model, input=text
    )
    vec = resp.data[0].embedding
    _embed_cache[key] = vec
    _cache_put("embed", settings.openai_embedding_model, text, vec)
    return vec


def chat(prompt: str, role: str = "agent", **kwargs: Any) -> str:
    """Run a chat completion (mocked when ``USE_MOCK_LLM=true``).

    ``role`` is forwarded to the mock router so each pipeline stage gets a
    role-appropriate stub; in real mode it is unused (a single user-message
    completion is sent). When ``settings.use_llm_cache=True`` responses
    are cached in the ``llm_cache`` MongoDB collection keyed by a
    deterministic hash of (model, role, prompt); cache hits do **not**
    bump the call counter.
    """
    if settings.use_mock_llm:
        # See note in ``embed`` — replay first, generic stubs second.
        cached = _replay.lookup("chat", f"{role}\x1f{prompt}")
        if cached is not None:
            return cached
        return _mock.chat(prompt, role=role, **kwargs)
    cache_payload = f"{role}\x1f{prompt}"
    persisted = _cache_get("chat", settings.openai_chat_model, cache_payload)
    if persisted is not None:
        return persisted
    _bump()
    resp = _chat_client().chat.completions.create(
        model=settings.openai_chat_model,
        messages=[{"role": "user", "content": prompt}],
    )
    out = resp.choices[0].message.content or ""
    _cache_put("chat", settings.openai_chat_model, cache_payload, out)
    return out


# ---------------------------------------------------------------------------
# MongoDB-backed LLM response cache (settings.use_llm_cache).
# ---------------------------------------------------------------------------
# Keyed by sha256 of (kind, model, payload). ``payload`` is the input
# text for embeddings and ``f"{role}\x1f{prompt}"`` for chat. Cache hits
# do not bump the call counter, preserving its meaning ("real API calls
# made") and the G9 replay invariant.

import hashlib  # noqa: E402  — kept near the cache helpers


def _cache_key(kind: str, model: str, payload: str) -> str:
    h = hashlib.sha256()
    h.update(kind.encode("utf-8"))
    h.update(b"\x1e")
    h.update(model.encode("utf-8"))
    h.update(b"\x1e")
    h.update(payload.encode("utf-8"))
    return h.hexdigest()


def _cache_get(kind: str, model: str, payload: str) -> Any | None:
    if not settings.use_llm_cache:
        return None
    try:
        from src.db.client import get_db

        row = get_db().llm_cache.find_one(
            {"cache_key": _cache_key(kind, model, payload)},
            {"_id": 0, "response": 1},
        )
    except Exception as exc:  # noqa: BLE001 — cache must never fail the pipeline
        log.warning("llm_cache read failed: %s", exc)
        return None
    return row["response"] if row else None


def _cache_put(kind: str, model: str, payload: str, response: Any) -> None:
    if not settings.use_llm_cache:
        return
    try:
        from datetime import datetime, timezone

        from src.db.client import get_db

        get_db().llm_cache.update_one(
            {"cache_key": _cache_key(kind, model, payload)},
            {
                "$set": {
                    "kind": kind,
                    "model": model,
                    "response": response,
                    "updated_at": datetime.now(timezone.utc),
                    # Truncated preview of the input so the collection is
                    # human-browsable in Atlas Data Explorer / Compass.
                    "preview": payload[:160],
                },
                "$setOnInsert": {
                    "created_at": datetime.now(timezone.utc),
                },
                "$inc": {"hits": 0},
            },
            upsert=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("llm_cache write failed: %s", exc)
