"""Progress event bus for live UI feedback during pipeline runs.

The pipeline emits structured progress events via :func:`emit`; consumers
(e.g. the Streamlit app) install a callback with :func:`set_listener` for
the duration of a run. When no listener is installed, ``emit`` is a no-op
so the CLI path is unaffected.

Events are best-effort UI hints — the database remains the authoritative
source of truth (see ``events`` collection).

Event kinds (info payload shape):
  pipeline_start       {prompt}
  stage_start          {stage}                 # decompose|execute|synthesise|...
  stage_end            {stage}
  decomposed           {n_subtasks, subtasks}  # subtasks: [{id,title,deps}]
  subtask_start        {subtask_id, title, idx, total}
  candidates_found     {subtask_id, n}
  coalition_formed     {subtask_id, skills, agents, rationale}
                       # skills: [{skill_id,name,solo}]
                       # agents: [{agent_id,score,skills_contributed}]
  round_posted         {subtask_id, round, sender}
  subtask_end          {subtask_id}
  pipeline_end         {run_id, summary}
"""
from __future__ import annotations

import contextlib
from typing import Any, Callable, Iterator

_listener: Callable[[str, dict[str, Any]], None] | None = None


def emit(kind: str, info: dict[str, Any] | None = None) -> None:
    """Forward a progress event to the installed listener (no-op if none).

    Listener exceptions are swallowed so a failing UI never crashes the
    pipeline.
    """
    if _listener is None:
        return
    try:
        _listener(kind, info or {})
    except Exception:  # noqa: BLE001 — UI must not crash the pipeline
        pass


@contextlib.contextmanager
def set_listener(
    fn: Callable[[str, dict[str, Any]], None] | None,
) -> Iterator[None]:
    """Install ``fn`` as the global progress listener for the duration of the block."""
    global _listener
    prev = _listener
    _listener = fn
    try:
        yield
    finally:
        _listener = prev
