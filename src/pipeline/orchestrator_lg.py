"""LangGraph backend for the design pipeline.

This module is an opt-in, parallel implementation of the same 9-stage
pipeline that lives in :mod:`src.pipeline.orchestrator`. It is selected
at import time when ``settings.use_langgraph`` is true.

Design rules (see ``docs/LANGGRAPH.md`` and ``docs/HANDOVER.md`` \u00a712):

* Every node is a thin wrapper around the **existing** stage function.
  No business logic, prompts, or DB writes live here.
* Every stage emits ``stage_start`` / ``stage_end`` via
  :func:`src.core.progress.emit` so the Streamlit live-progress pane works
  unchanged.
* The graph is intentionally linear today; conditional / parallel edges
  are future work.
* MongoDB row shape is byte-identical to the function backend because we
  share helpers via :mod:`src.pipeline._run_utils`.

Public entry point: :func:`run_pipeline` \u2014 same signature and return
shape as :func:`src.pipeline.orchestrator.run_pipeline`.
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.core.progress import emit
from src.pipeline._run_utils import (
    build_summary,
    ensure_run,
    finalise_run,
    topo_order,
    upstream_outputs,
)
from src.pipeline.decomposer import decompose
from src.pipeline.execution import execute_subtask
from src.pipeline.reporter import build_report
from src.pipeline.reputation import apply_run_reputations
from src.pipeline.surveyor import estimate
from src.pipeline.synthesis import synthesise
from src.pipeline.validation import validate
from src.pipeline.validator_spec import derive_validation_spec
from src.pipeline.visualiser import build_geometry

log = logging.getLogger(__name__)


class GraphState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes.

    Each node returns a *partial* dict; LangGraph merges into the running
    state. ``total=False`` lets us add fields lazily without declaring
    them up front.
    """

    run_id: str
    prompt: str
    ordered: list[dict]
    criteria: list[dict]
    spec: dict
    validation: dict
    cost: dict
    report_md: str
    n_reputation_updates: int
    summary: dict


# --------------------------------------------------------------------------
# Nodes \u2014 each one corresponds 1:1 to a stage in the function backend.
# Each node:
#   1. emits stage_start
#   2. calls the existing stage function
#   3. emits stage_end
#   4. returns a partial GraphState dict
# --------------------------------------------------------------------------


def ensure_run_node(state: GraphState) -> GraphState:
    run_id = ensure_run(state["prompt"])
    log.info("langgraph pipeline run_id=%s prompt=%r", run_id, state["prompt"])
    emit("pipeline_start", {"prompt": state["prompt"], "run_id": run_id})
    return {"run_id": run_id}


def decompose_node(state: GraphState) -> GraphState:
    emit("stage_start", {"stage": "decompose"})
    subtasks = decompose(state["run_id"], state["prompt"])
    ordered = topo_order(subtasks)
    emit("decomposed", {
        "n_subtasks": len(ordered),
        "subtasks": [
            {"id": st["subtask_id"], "title": st["title"],
             "deps": st.get("depends_on", [])}
            for st in ordered
        ],
    })
    emit("stage_end", {"stage": "decompose"})
    return {"ordered": ordered}


def validator_spec_node(state: GraphState) -> GraphState:
    emit("stage_start", {"stage": "validator_spec"})
    val_spec = derive_validation_spec(state["run_id"], state["prompt"])
    criteria = val_spec.get("criteria", [])
    emit("validation_spec_derived", {"n_criteria": len(criteria)})
    emit("stage_end", {"stage": "validator_spec"})
    return {"criteria": criteria}


def execute_node(state: GraphState) -> GraphState:
    emit("stage_start", {"stage": "execute"})
    run_id = state["run_id"]
    ordered = state["ordered"]
    criteria = state.get("criteria", [])
    total = len(ordered)
    for idx, st in enumerate(ordered, 1):
        st_doc = {**st, "run_id": run_id}
        upstream = upstream_outputs(run_id, st_doc)
        emit("subtask_start", {
            "subtask_id": st["subtask_id"], "title": st["title"],
            "idx": idx, "total": total,
        })
        execute_subtask(run_id, st_doc, upstream, criteria=criteria)
        emit("subtask_end", {"subtask_id": st["subtask_id"]})
    emit("stage_end", {"stage": "execute"})
    return {}


def synthesise_node(state: GraphState) -> GraphState:
    emit("stage_start", {"stage": "synthesise"})
    spec = synthesise(state["run_id"], state["prompt"])
    emit("stage_end", {"stage": "synthesise"})
    return {"spec": spec}


def validate_node(state: GraphState) -> GraphState:
    emit("stage_start", {"stage": "validate"})
    validation = validate(state["run_id"], state["spec"])
    emit("stage_end", {"stage": "validate"})
    return {"validation": validation}


def estimate_node(state: GraphState) -> GraphState:
    emit("stage_start", {"stage": "estimate"})
    cost = estimate(state["run_id"], state["spec"])
    emit("stage_end", {"stage": "estimate"})
    return {"cost": cost}


def visualise_node(state: GraphState) -> GraphState:
    emit("stage_start", {"stage": "visualise"})
    build_geometry(state["run_id"], state["spec"])
    emit("stage_end", {"stage": "visualise"})
    return {}


def report_node(state: GraphState) -> GraphState:
    emit("stage_start", {"stage": "report"})
    md = build_report(
        state["run_id"], state["prompt"], state["spec"],
        state["validation"], state["cost"],
    )
    emit("stage_end", {"stage": "report"})
    return {"report_md": md}


def reputation_node(state: GraphState) -> GraphState:
    emit("stage_start", {"stage": "reputation"})
    n_rep = apply_run_reputations(
        state["run_id"], state["validation"]["overall_status"],
    )
    emit("stage_end", {"stage": "reputation"})
    return {"n_reputation_updates": n_rep}


def finalise_node(state: GraphState) -> GraphState:
    finalise_run(
        state["run_id"], state["ordered"],
        state["validation"], state["cost"],
    )
    summary = build_summary(
        state["run_id"], state["ordered"], state["validation"],
        state["cost"], state["n_reputation_updates"], state["report_md"],
    )
    emit("pipeline_end", {"run_id": state["run_id"], "summary": summary})
    return {"summary": summary}


# --------------------------------------------------------------------------
# Graph construction \u2014 declarative wiring of the linear pipeline.
# --------------------------------------------------------------------------


def build_graph():
    """Compile the LangGraph state graph.

    Linear DAG today. Conditional edges (e.g. skip cost on validation
    fail) and parallel ``Send`` over subtasks are future work; see
    ``docs/LANGGRAPH.md`` \u00a75.4.
    """
    g = StateGraph(GraphState)
    g.add_node("ensure_run", ensure_run_node)
    g.add_node("decompose", decompose_node)
    g.add_node("validator_spec", validator_spec_node)
    g.add_node("execute", execute_node)
    g.add_node("synthesise", synthesise_node)
    g.add_node("validate", validate_node)
    g.add_node("estimate", estimate_node)
    g.add_node("visualise", visualise_node)
    g.add_node("report", report_node)
    g.add_node("reputation", reputation_node)
    g.add_node("finalise", finalise_node)

    g.set_entry_point("ensure_run")
    g.add_edge("ensure_run", "decompose")
    g.add_edge("decompose", "validator_spec")
    g.add_edge("validator_spec", "execute")
    g.add_edge("execute", "synthesise")
    g.add_edge("synthesise", "validate")
    g.add_edge("validate", "estimate")
    g.add_edge("estimate", "visualise")
    g.add_edge("visualise", "report")
    g.add_edge("report", "reputation")
    g.add_edge("reputation", "finalise")
    g.add_edge("finalise", END)

    return g.compile()


# Compile once at import time. The graph is stateless across runs;
# state is per-invocation.
_GRAPH = build_graph()


def run_pipeline(prompt: str) -> dict[str, Any]:
    """LangGraph-backed equivalent of :func:`src.pipeline.orchestrator.run_pipeline`.

    Same signature, same return shape, same MongoDB row shape, same
    progress emissions. The only difference is *how* stages are wired.
    """
    final_state: GraphState = _GRAPH.invoke({"prompt": prompt})
    return final_state["summary"]
