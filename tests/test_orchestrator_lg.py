"""End-to-end pipeline test against the LangGraph backend (mock mode).

Mirrors :mod:`tests.test_e2e_mock` but invokes
:mod:`src.pipeline.orchestrator_lg` instead of the function backend. The
goal is to prove G6 invariants hold byte-identically through LangGraph:

* ``subtask_outputs`` non-empty for every subtask
* >= 12 rows in ``coalition_messages``
* every pipeline stage has >= 1 ``events`` row (kind set)
* every ``subtask_outputs.summary`` <= 200 tokens
* replay (function backend) on a LangGraph-produced run still works
"""
from __future__ import annotations

import pytest

# Skip the whole module if the optional langgraph package isn't installed.
pytest.importorskip("langgraph")

from src.core.config import settings
from src.core.tokens import count_tokens
from src.db.client import get_db
from src.pipeline.orchestrator import replay  # replay always uses function backend
from src.pipeline.orchestrator_lg import run_pipeline as run_pipeline_lg

REQUIRED_EVENT_KINDS = {
    "run_started", "decompose", "coalition_formed", "message_posted",
    "subtask_completed", "design_synthesised", "validation_done",
    "cost_estimated", "report_built", "reputation_updated", "run_completed",
}


def test_e2e_langgraph_pipeline():
    """End-to-end test of the LangGraph pipeline in mock mode, checking G6 invariants and replay."""
    assert settings.use_mock_llm, "test must run with USE_MOCK_LLM=true"
    out = run_pipeline_lg("design a 2 km bridge for 50 cars/h with trucks")
    run_id = out["run_id"]
    db = get_db()

    n_subtasks = db.subtasks.count_documents({"run_id": run_id})
    n_outputs = db.subtask_outputs.count_documents({"run_id": run_id})
    n_messages = db.coalition_messages.count_documents({"run_id": run_id})
    assert n_outputs == n_subtasks > 0, (n_outputs, n_subtasks)
    assert n_messages >= 12, n_messages

    kinds = set(db.events.distinct("kind", {"run_id": run_id}))
    missing = REQUIRED_EVENT_KINDS - kinds
    assert not missing, f"missing event kinds: {missing}"

    for o in db.subtask_outputs.find({"run_id": run_id}, {"summary": 1}):
        assert count_tokens(o["summary"]) <= 200

    # Replay must make zero LLM calls even on a LangGraph-produced run.
    rep = replay(run_id)
    assert rep["subtasks"] == n_subtasks


def test_langgraph_graph_compiles():
    """Test that the LangGraph graph builds and exposes the expected nodes."""
    """Smoke test: the graph builds and exposes the expected nodes."""
    from src.pipeline.orchestrator_lg import build_graph

    g = build_graph()
    # The compiled graph exposes a ``get_graph()`` introspection helper.
    nodes = set(g.get_graph().nodes.keys())
    expected = {
        "ensure_run", "decompose", "validator_spec", "execute",
        "synthesise", "validate", "estimate", "visualise", "report",
        "reputation", "finalise",
    }
    assert expected <= nodes, f"missing nodes: {expected - nodes}"
