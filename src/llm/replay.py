"""File-backed replay cache for the demo (no OpenAI key, no MongoDB needed).

Loads ``data/llm_replay_cache.json`` (produced by
``scripts/export_llm_cache.py``) and exposes a single ``lookup`` helper that
mirrors the lookup contract used in ``src/llm/openai_client.py``.

Design:

* The JSON file is keyed by the same ``sha256(kind, model, payload)`` hash
  used by the live MongoDB cache. We rehash here using the **captured**
  model names from the JSON's ``meta`` block (not the live ``settings``
  values) so a model swap in ``.env`` won't silently miss every entry.
* Loading is lazy and refreshes when the JSON changes on disk. Missing file
  → empty cache; callers decide whether to fall back or fail strictly.
* This module never reads from MongoDB and never imports the OpenAI SDK,
  so the published demo can run with neither configured.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# data/llm_replay_cache.json relative to repo root (this file lives in src/llm).
_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "llm_replay_cache.json"

_loaded: bool = False
_loaded_mtime_ns: int | None = None
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
    global _loaded, _loaded_mtime_ns, _entries, _meta
    try:
        mtime_ns = path.stat().st_mtime_ns
    except FileNotFoundError:
        mtime_ns = None

    if _loaded and _loaded_mtime_ns == mtime_ns:
        return
    _loaded = True
    _loaded_mtime_ns = mtime_ns
    _entries = {}
    _meta = {}
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
    """Return the metadata block from the loaded JSON (empty if not loaded).

    Returns:
        dict[str, Any]: The metadata block (may be empty).
    """
    _load()
    return dict(_meta)


def is_available() -> bool:
    """Return True if the replay cache file was found and contains entries.

    Returns:
        bool: True if the cache is loaded and non-empty.
    """
    _load()
    return len(_entries) > 0


def lookup(kind: str, payload: str) -> Any | None:
    """Return the captured response for ``(kind, payload)``, or ``None``.

    ``kind`` is ``"chat"`` or ``"embed"``. The model name is taken from
    the captured ``meta`` block, **not** from live settings, so the lookup
    is robust to ``.env`` drift between capture and replay.

    Args:
        kind: The type of response ("chat" or "embed").
        payload: The prompt or text to look up.

    Returns:
        Any | None: The captured response, or None if not found.
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


def lookup_chat_by_role(role: str) -> Any | None:
    """Return a recorded chat response for ``role`` when exact prompts drift.

    This is intentionally weaker than :func:`lookup` and should only be used
    for late-stage narrative roles whose prompts include volatile deterministic
    numbers. Council messages should use exact prompt hashes.
    """
    _load()
    if not _entries:
        return None
    prefix = f"{role}\x1f"
    match = None
    for row in _entries.values():
        if row.get("kind") != "chat":
            continue
        preview = row.get("preview", "")
        if isinstance(preview, str) and preview.startswith(prefix):
            match = row
    return match.get("response") if match else None


def agent_order_for(
    subtask_id: str,
    title: str,
    agent_ids: list[str],
) -> list[str] | None:
    """Return the recorded replay order for a subtask's agent set, if known.

    The file-backed cache stores only prompt previews, not full prompts, but
    agent previews include the stable agent id plus ``subtask_id`` and title.
    When replay-mode recomputes the same agent set in a different order, this
    lets the pipeline restore the order used by the captured live run so the
    downstream marshal/agent prompt hashes remain cache hits.
    """
    _load()
    if not _entries or not agent_ids:
        return None

    target = set(agent_ids)
    n_agents = len(agent_ids)
    if len(target) != n_agents:
        return None

    marker = f"contributing to subtask {subtask_id}\n({title})"
    seen: list[str] = []
    for row in _entries.values():
        if row.get("kind") != "chat":
            continue
        preview = row.get("preview", "")
        if not isinstance(preview, str):
            continue
        if not preview.startswith("agent\x1f") or marker not in preview:
            continue
        match = re.search(r"agent (agent_\d+), contributing", preview)
        if match and match.group(1) in target:
            seen.append(match.group(1))

    matched_order: list[str] | None = None
    for i in range(0, max(len(seen) - n_agents + 1, 0)):
        window = seen[i:i + n_agents]
        if len(set(window)) == n_agents and set(window) == target:
            matched_order = window
    return matched_order
