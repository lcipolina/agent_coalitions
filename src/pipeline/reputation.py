"""Reputation updates after each run.

For every agent that participated, write a reputation_updates row and bump
the agent's running ``reputation`` (clipped to [0,1]).

Heuristic deltas:
  +0.02 if validation overall_status is conceptual_pass
  +0.01 if conceptual_pass_with_warnings
  -0.02 if conceptual_fail
"""
from __future__ import annotations

from src.db.client import get_db
from src.db.writes import insert_with_event

_DELTA_BY_STATUS = {
    "conceptual_pass": +0.02,
    "conceptual_pass_with_warnings": +0.01,
    "conceptual_fail": -0.02,
}


def apply_run_reputations(run_id: str, overall_status: str) -> int:
    db = get_db()
    delta = _DELTA_BY_STATUS.get(overall_status, 0.0)

    participated: set[str] = set()
    for a in db.assignments.find({"run_id": run_id}, {"coalition_agent_ids": 1}):
        participated.update(a.get("coalition_agent_ids", []))

    n = 0
    for agent_id in participated:
        agent = db.agents.find_one({"agent_id": agent_id}, {"reputation": 1})
        if not agent:
            continue
        new_rep = max(0.0, min(1.0, agent["reputation"] + delta))
        db.agents.update_one(
            {"agent_id": agent_id},
            {"$set": {"reputation": new_rep},
             "$inc": {"runs_participated": 1,
                      "runs_succeeded": 1 if delta > 0 else 0}},
        )
        insert_with_event(
            "reputation_updates",
            {"run_id": run_id, "agent_id": agent_id, "delta": delta,
             "reason": f"run_{overall_status}"},
            event_kind="reputation_updated",
            event_payload={"agent_id": agent_id, "delta": delta},
        )
        n += 1
    return n
