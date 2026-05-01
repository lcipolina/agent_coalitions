"""Pipeline orchestrator (plain function pipeline — escape hatch per Amendment 3.14).

Stages (sequential):
  1. ensure_run         -> insert runs row
  2. decompose          -> subtasks rows
  3. execute_subtasks   -> assignments + coalition_messages + subtask_outputs
  4. synthesise         -> design_specs row
  5. validate           -> validation_results row
  6. estimate_cost      -> cost_estimates row
  7. visualise          -> artifacts row (kind=geometry_json)
  8. build_report       -> artifacts row + runs.final_report_md
  9. apply_reputations  -> reputation_updates rows

Replay path: if ``replay=True`` we skip stages 2-9 and only re-read the
existing rows for the given run_id. The G9 invariant
(``openai_client.call_counter == 0``) is asserted by the caller.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.config import settings
from src.db.client import get_db
from src.db.writes import insert_with_event, log_event
from src.pipeline.decomposer import decompose
from src.pipeline.execution import execute_subtask
from src.llm import openai_client
from src.pipeline.reporter import build_report
from src.pipeline.reputation import apply_run_reputations
from src.pipeline.surveyor import estimate
from src.pipeline.synthesis import synthesise
from src.pipeline.validation import validate
from src.pipeline.visualiser import build_geometry
from src.progress import emit

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y_%m_%d')}_{uuid.uuid4().hex[:8]}"


def _ensure_run(prompt: str) -> str:
    run_id = _new_run_id()
    insert_with_event(
        "runs",
        {
            "run_id": run_id,
            "prompt": prompt,
            "status": "running",
            "use_mock_llm": settings.use_mock_llm,
            "config": {"seed": settings.seed, "git_sha": None,
                       "use_mock_llm": settings.use_mock_llm},
            "started_at": _now(),
        },
        event_kind="run_started",
    )
    return run_id


def _topo_order(subtasks: list[dict]) -> list[dict]:
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


def _upstream_outputs(run_id: str, subtask: dict) -> list[dict]:
    deps = subtask.get("depends_on", [])
    if not deps:
        return []
    return list(get_db().subtask_outputs.find(
        {"run_id": run_id, "subtask_id": {"$in": deps}}, {"_id": 0},
    ))


def run_pipeline(prompt: str) -> dict[str, Any]:
    run_id = _ensure_run(prompt)
    log.info("pipeline run_id=%s prompt=%r", run_id, prompt)
    emit("pipeline_start", {"prompt": prompt, "run_id": run_id})

    # Stage 2: decompose.
    emit("stage_start", {"stage": "decompose"})
    subtasks = decompose(run_id, prompt)
    ordered = _topo_order(subtasks)
    emit("decomposed", {
        "n_subtasks": len(ordered),
        "subtasks": [
            {"id": st["subtask_id"], "title": st["title"],
             "deps": st.get("depends_on", [])}
            for st in ordered
        ],
    })
    emit("stage_end", {"stage": "decompose"})

    # Stage 3: execute subtasks (each writes assignment + messages + output).
    emit("stage_start", {"stage": "execute"})
    total = len(ordered)
    for idx, st in enumerate(ordered, 1):
        st_doc = {**st, "run_id": run_id}
        upstream = _upstream_outputs(run_id, st_doc)
        emit("subtask_start", {
            "subtask_id": st["subtask_id"], "title": st["title"],
            "idx": idx, "total": total,
        })
        execute_subtask(run_id, st_doc, upstream)
        emit("subtask_end", {"subtask_id": st["subtask_id"]})
    emit("stage_end", {"stage": "execute"})

    # Stage 4: synthesise design spec.
    emit("stage_start", {"stage": "synthesise"})
    spec = synthesise(run_id, prompt)
    emit("stage_end", {"stage": "synthesise"})
    # Stage 5: validate.
    emit("stage_start", {"stage": "validate"})
    validation = validate(run_id, spec)
    emit("stage_end", {"stage": "validate"})
    # Stage 6: cost.
    emit("stage_start", {"stage": "estimate"})
    cost = estimate(run_id, spec)
    emit("stage_end", {"stage": "estimate"})
    # Stage 7: visualise (spec -> 3D geometry primitives).
    emit("stage_start", {"stage": "visualise"})
    build_geometry(run_id, spec)
    emit("stage_end", {"stage": "visualise"})
    # Stage 8: report.
    emit("stage_start", {"stage": "report"})
    md = build_report(run_id, prompt, spec, validation, cost)
    emit("stage_end", {"stage": "report"})
    # Stage 8: reputation.
    emit("stage_start", {"stage": "reputation"})
    n_rep = apply_run_reputations(run_id, validation["overall_status"])
    emit("stage_end", {"stage": "reputation"})

    # Finalise runs row.
    db = get_db()
    db.runs.update_one(
        {"run_id": run_id},
        {"$set": {
            "status": "completed",
            "completed_at": _now(),
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

    summary = {
        "run_id": run_id,
        "subtasks": len(ordered),
        "validation": validation["overall_status"],
        "cost_total": cost["total"],
        "reputation_updates": n_rep,
        "report_md_chars": len(md),
    }
    emit("pipeline_end", {"run_id": run_id, "summary": summary})
    return summary


def replay(run_id: str) -> dict[str, Any]:
    """Re-read everything from Mongo. Must NOT trigger any LLM call."""
    openai_client.reset_counter()
    db = get_db()
    log_event(run_id, "replay")
    out = {
        "run_id": run_id,
        "subtasks": db.subtasks.count_documents({"run_id": run_id}),
        "messages": db.coalition_messages.count_documents({"run_id": run_id}),
        "subtask_outputs": db.subtask_outputs.count_documents({"run_id": run_id}),
        "design_specs": db.design_specs.count_documents({"run_id": run_id}),
        "validation_results": db.validation_results.count_documents({"run_id": run_id}),
        "cost_estimates": db.cost_estimates.count_documents({"run_id": run_id}),
        "artifacts": db.artifacts.count_documents({"run_id": run_id}),
    }
    assert openai_client.call_counter() == 0, (
        f"replay must make 0 LLM calls, got {openai_client.call_counter()}"
    )
    return out
