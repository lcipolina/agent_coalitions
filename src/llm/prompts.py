"""Jinja2 prompt template loader.

Templates live next to this module in ``src/prompts/*.j2`` and are rendered
by short, kebab-style names: ``render("decomposer", prompt="...")`` resolves
to ``src/prompts/decomposer.j2``.

Rationale: keep all human-editable prompt copy out of Python source so a
designer can iterate on wording without touching code. In mock mode the
rendered string is built but never actually sent to a model — the mock
``chat()`` routes by ``role`` argument.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPTS_DIR)),
        autoescape=select_autoescape(default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )


def render(name: str, **context) -> str:
    """Render ``src/prompts/{name}.j2`` with the given context."""
    return _env().get_template(f"{name}.j2").render(**context)
