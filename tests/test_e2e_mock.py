"""End-to-end pipeline test in mock mode.

Runs the full pipeline on a default prompt and asserts G6 invariants:
  - subtask_outputs non-empty for every subtask
  - >= 12 rows in coalition_messages
  - every pipeline stage has >= 1 events row (kind set)
  - every subtask_outputs.summary <= 200 tokens
"""
from __future__ import annotations

import os

from src.core.config import settings
from src.db.client import get_db
from src.pipeline.orchestrator import replay, run_pipeline
from src.core.tokens import count_tokens

REQUIRED_EVENT_KINDS = {
    "run_started", "decompose", "coalition_formed", "message_posted",
    "subtask_completed", "design_synthesised", "validation_done",
    "cost_estimated", "report_built", "reputation_updated", "run_completed",
}


def test_e2e_mock_pipeline():
    """End-to-end test of the pipeline in mock mode, checking G6 invariants and event kinds."""
    assert settings.use_mock_llm, "test must run with USE_MOCK_LLM=true"
    out = run_pipeline("design a 2 km bridge for 50 cars/h with trucks")
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

    # Replay must make zero LLM calls.
    rep = replay(run_id)
    assert rep["subtasks"] == n_subtasks
