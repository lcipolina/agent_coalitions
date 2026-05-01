"""Reputation updates after each run.

For every agent that participated, write a reputation_updates row and bump
the agent's running ``reputation`` (clipped to [0,1]).

Heuristic per-run base delta:
  +0.04 if validation overall_status is conceptual_pass
  +0.02 if conceptual_pass_with_warnings
  -0.04 if conceptual_fail

The base is then scaled per agent by:
  load_factor   = subtasks_participated / total_subtasks_in_run    (in [0,1])
  quality_factor= mean(contribution_score across subtasks)         (typically [0,1])
  delta_agent   = base * (0.5 + 0.5 * load_factor) * (0.5 + 0.5 * quality_factor)

so an agent that appears in more subtasks and is ranked higher inside its
coalitions accrues a larger delta than a single-subtask, low-score agent.
This keeps the reputation tab visually informative across runs.
"""
from __future__ import annotations

from src.db.client import get_db
from src.db.writes import insert_with_event

_BASE_DELTA_BY_STATUS = {
    "conceptual_pass": +0.04,
    "conceptual_pass_with_warnings": +0.02,
    "conceptual_fail": -0.04,
}


def apply_run_reputations(run_id: str, overall_status: str) -> int:
    """Compute and persist per-agent reputation deltas for one completed run.

    Returns the number of ``reputation_updates`` rows written.
    """
    db = get_db()
    base = _BASE_DELTA_BY_STATUS.get(overall_status, 0.0)

    # Aggregate per-agent participation + average contribution score.
    assigns = list(db.assignments.find(
        {"run_id": run_id},
        {"_id": 0, "subtask_id": 1, "coalition_agent_ids": 1,
         "contribution_scores": 1},
    ))
    n_subtasks = max(len(assigns), 1)

    per_agent_subtasks: dict[str, set[str]] = {}
    per_agent_scores: dict[str, list[float]] = {}
    for a in assigns:
        for cs in a.get("contribution_scores", []):
            aid = cs["agent_id"]
            per_agent_subtasks.setdefault(aid, set()).add(a["subtask_id"])
            per_agent_scores.setdefault(aid, []).append(float(cs.get("score", 0.0)))
        # marshal-only fallback assignments still count as participation
        for aid in a.get("coalition_agent_ids", []):
            per_agent_subtasks.setdefault(aid, set()).add(a["subtask_id"])
            per_agent_scores.setdefault(aid, [])

    n = 0
    for agent_id, st_ids in per_agent_subtasks.items():
        agent = db.agents.find_one({"agent_id": agent_id}, {"reputation": 1})
        if not agent:
            continue
        scores = per_agent_scores.get(agent_id) or [0.5]
        load_factor = len(st_ids) / n_subtasks
        quality_factor = sum(scores) / len(scores)
        delta = round(
            base * (0.5 + 0.5 * load_factor) * (0.5 + 0.5 * quality_factor), 4,
        )
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
             "subtasks_participated": sorted(st_ids),
             "mean_contribution_score": round(quality_factor, 3),
             "reason": f"run_{overall_status}"},
            event_kind="reputation_updated",
            event_payload={"agent_id": agent_id, "delta": delta},
        )
        n += 1
    return n
