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
from typing import Any

from src.core.config import settings
from src.db.client import get_db
from src.db.seed import seed_agents
from src.db.writes import log_event
from src.llm import replay as llm_replay
from src.pipeline._run_utils import (
    build_summary,
    ensure_run,
    finalise_run,
    topo_order,
    upstream_outputs,
)
from src.pipeline.decomposer import decompose
from src.pipeline.execution import execute_subtask
from src.llm import openai_client
from src.pipeline.reporter import build_report
from src.pipeline.reputation import apply_run_reputations
from src.pipeline.surveyor import estimate
from src.pipeline.synthesis import synthesise
from src.pipeline.validation import validate
from src.pipeline.validator_spec import derive_validation_spec
from src.pipeline.visualiser import build_geometry
from src.core.progress import emit

log = logging.getLogger(__name__)


def run_pipeline(prompt: str) -> dict[str, Any]:
    """Run the full 9-stage pipeline for ``prompt`` and return a summary dict.

    Each stage writes its own MongoDB rows (and ≥ 1 ``events`` row, per G6).
    Progress hints are emitted via :mod:`src.core.progress` for live UIs.
    """
    if settings.use_mock_llm and llm_replay.is_available():
        seed_agents()

    run_id = ensure_run(prompt)
    log.info("pipeline run_id=%s prompt=%r", run_id, prompt)
    emit("pipeline_start", {"prompt": prompt, "run_id": run_id})

    # Stage 2: decompose.
    emit("stage_start", {"stage": "decompose"})
    subtasks = decompose(run_id, prompt)
    ordered = topo_order(subtasks)
    emit(
        "decomposed",
        {
            "n_subtasks": len(ordered),
            "subtasks": [
                {
                    "id": st["subtask_id"],
                    "title": st["title"],
                    "deps": st.get("depends_on", []),
                }
                for st in ordered
            ],
        },
    )
    emit("stage_end", {"stage": "decompose"})

    # Stage 2.5: derive validation spec from the prompt and persist on runs.
    # The criteria are also passed into every marshal kickoff so coalitions
    # know what they will ultimately be judged on.
    emit("stage_start", {"stage": "validator_spec"})
    val_spec = derive_validation_spec(run_id, prompt)
    criteria = val_spec.get("criteria", [])
    emit("validation_spec_derived", {"n_criteria": len(criteria)})
    emit("stage_end", {"stage": "validator_spec"})

    # Stage 3: execute subtasks (each writes assignment + messages + output).
    emit("stage_start", {"stage": "execute"})
    total = len(ordered)
    for idx, st in enumerate(ordered, 1):
        st_doc = {**st, "run_id": run_id}
        upstream = upstream_outputs(run_id, st_doc)
        emit(
            "subtask_start",
            {
                "subtask_id": st["subtask_id"],
                "title": st["title"],
                "idx": idx,
                "total": total,
            },
        )
        execute_subtask(run_id, st_doc, upstream, criteria=criteria)
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
    # Stage 9: reputation.
    emit("stage_start", {"stage": "reputation"})
    n_rep = apply_run_reputations(run_id, validation["overall_status"])
    emit("stage_end", {"stage": "reputation"})

    # Finalise runs row.
    finalise_run(run_id, ordered, validation, cost)

    summary = build_summary(run_id, ordered, validation, cost, n_rep, md)
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
    assert (
        openai_client.call_counter() == 0
    ), f"replay must make 0 LLM calls, got {openai_client.call_counter()}"
    return out
