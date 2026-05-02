"""Shared helpers for both pipeline orchestrators (function + LangGraph).

These were originally private to ``src/pipeline/orchestrator.py``. They are
extracted here so the LangGraph backend (``orchestrator_lg.py``) can reuse
them verbatim and both orchestrators stay byte-identical at the MongoDB row
level.

Nothing in this module is LangGraph-aware. Side-effects are the same as
before: each helper writes / reads MongoDB and / or emits progress events
through ``src.core.progress``.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.core.config import settings
from src.db.client import get_db
from src.db.writes import insert_with_event, log_event

log = logging.getLogger(__name__)


def now() -> datetime:
    """UTC ``datetime.now`` shared by both orchestrators."""
    return datetime.now(timezone.utc)


def new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y_%m_%d')}_{uuid.uuid4().hex[:8]}"


def ensure_run(prompt: str) -> str:
    """Insert the ``runs`` row for a new pipeline invocation."""
    run_id = new_run_id()
    insert_with_event(
        "runs",
        {
            "run_id": run_id,
            "prompt": prompt,
            "status": "running",
            "use_mock_llm": settings.use_mock_llm,
            "config": {"seed": settings.seed, "git_sha": None,
                       "use_mock_llm": settings.use_mock_llm},
            "started_at": now(),
        },
        event_kind="run_started",
    )
    return run_id


def topo_order(subtasks: list[dict]) -> list[dict]:
    """Topologically sort decomposed subtasks by ``depends_on`` edges."""
    by_id = {st["subtask_id"]: st for st in subtasks}
    seen: set[str] = set()
    out: list[dict] = []

    def visit(sid: str) -> None:
        if sid in seen:
            return
        for dep in by_id[sid].get("depends_on", []):
            visit(dep)
        seen.add(sid)
        out.append(by_id[sid])

    for sid in by_id:
        visit(sid)
    return out


def upstream_outputs(run_id: str, subtask: dict) -> list[dict]:
    """Read the ``subtask_outputs`` rows the given subtask depends on."""
    deps = subtask.get("depends_on", [])
    if not deps:
        return []
    return list(get_db().subtask_outputs.find(
        {"run_id": run_id, "subtask_id": {"$in": deps}}, {"_id": 0},
    ))


def finalise_run(
    run_id: str, ordered: list[dict], validation: dict, cost: dict,
) -> None:
    """Mark the run completed and write the ``run_completed`` event row.

    Shared by both orchestrators; identical body to the tail of the
    function-pipeline ``run_pipeline``.
    """
    db = get_db()
    db.runs.update_one(
        {"run_id": run_id},
        {"$set": {
            "status": "completed",
            "completed_at": now(),
            "summary_metrics": {
                "n_subtasks": len(ordered),
                "n_assignments": db.assignments.count_documents({"run_id": run_id}),
                "n_messages": db.coalition_messages.count_documents({"run_id": run_id}),
                "validation_status": validation["overall_status"],
                "estimated_cost_eur": cost["total"],
            },
        }},
    )
    log_event(run_id, "run_completed",
              {"validation": validation["overall_status"], "cost": cost["total"]})


def build_summary(
    run_id: str, ordered: list[dict], validation: dict, cost: dict,
    n_rep: int, report_md: str,
) -> dict[str, Any]:
    """The dict shape both orchestrators return to the caller."""
    return {
        "run_id": run_id,
        "subtasks": len(ordered),
        "validation": validation["overall_status"],
        "cost_total": cost["total"],
        "reputation_updates": n_rep,
        "report_md_chars": len(report_md),
    }
