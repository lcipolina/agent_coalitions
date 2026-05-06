"""File-backed replay cache for the demo (no OpenAI key, no MongoDB needed).

Loads ``data/llm_replay_cache.json`` (produced by
``scripts/export_llm_cache.py``) and exposes a single ``lookup`` helper that
mirrors the lookup contract used in ``src/llm/openai_client.py``.

Design:

* The JSON file is keyed by the same ``sha256(kind, model, payload)`` hash
  used by the live MongoDB cache. We rehash here using the **captured**
  model names from the JSON's ``meta`` block (not the live ``settings``
  values) so a model swap in ``.env`` won't silently miss every entry.
* Loading is lazy and memoised. Missing file → empty cache (the mock
  stubs in ``src/llm/mock.py`` are still available as a fallback).
* This module never reads from MongoDB and never imports the OpenAI SDK,
  so the published demo can run with neither configured.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# data/llm_replay_cache.json relative to repo root (this file lives in src/llm).
_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "llm_replay_cache.json"

_loaded: bool = False
_entries: dict[str, dict[str, Any]] = {}
_meta: dict[str, Any] = {}


def _cache_key(kind: str, model: str, payload: str) -> str:
    """Mirror of ``openai_client._cache_key`` — must stay byte-identical."""
    h = hashlib.sha256()
    h.update(kind.encode("utf-8"))
    h.update(b"\x1e")
    h.update(model.encode("utf-8"))
    h.update(b"\x1e")
    h.update(payload.encode("utf-8"))
    return h.hexdigest()


def _load(path: Path = _DEFAULT_PATH) -> None:
    global _loaded, _entries, _meta
    if _loaded:
        return
    _loaded = True
    if not path.exists():
        log.info("replay cache not found at %s — running with mock stubs only", path)
        return
    try:
        data = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("replay cache at %s could not be parsed: %s", path, exc)
        return
    _entries = data.get("entries", {}) or {}
    _meta = data.get("meta", {}) or {}
    log.info(
        "replay cache loaded: %d entries (chat=%s, embed=%s)",
        len(_entries),
        _meta.get("chat_model"),
        _meta.get("embed_model"),
    )


def meta() -> dict[str, Any]:
    """Return the metadata block from the loaded JSON (empty if not loaded)."""
    _load()
    return dict(_meta)


def is_available() -> bool:
    """True if the replay cache file was found and contains entries."""
    _load()
    return len(_entries) > 0


def lookup(kind: str, payload: str) -> Any | None:
    """Return the captured response for ``(kind, payload)``, or ``None``.

    ``kind`` is ``"chat"`` or ``"embed"``. The model name is taken from
    the captured ``meta`` block, **not** from live settings, so the lookup
    is robust to ``.env`` drift between capture and replay.
    """
    _load()
    if not _entries:
        return None
    if kind == "chat":
        model = _meta.get("chat_model")
    elif kind == "embed":
        model = _meta.get("embed_model")
    else:
        return None
    if not model:
        return None
    key = _cache_key(kind, model, payload)
    row = _entries.get(key)
    if row is None:
        return None
    return row.get("response")
