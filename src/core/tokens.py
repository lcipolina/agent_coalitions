"""Token counting / truncation helpers using tiktoken (cl100k_base)."""
"""
Token counting / truncation helpers using tiktoken (cl100k_base).

This module provides helpers for counting tokens and truncating text to a token limit,
using the cl100k_base encoding (compatible with OpenAI models).

How to use:
    Import and call count_tokens(text) or truncate_to_tokens(text, max_tokens).
    This module is used by pipeline and agent modules for token management.

Not intended to be run as a standalone script.
"""
from __future__ import annotations

from functools import lru_cache

SUBTASK_OUTPUT_TOKEN_CAP = 200  # MVP_DESIGN amendment 3.2


@lru_cache(maxsize=1)
def _enc():
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Return the number of cl100k_base tokens in ``text``."""
    return len(_enc().encode(text))


def truncate_to_tokens(text: str, max_tokens: int = SUBTASK_OUTPUT_TOKEN_CAP) -> str:
    """Decode-truncate ``text`` so its token count is at most ``max_tokens``."""
    enc = _enc()
    ids = enc.encode(text)
    if len(ids) <= max_tokens:
        return text
    return enc.decode(ids[:max_tokens])
