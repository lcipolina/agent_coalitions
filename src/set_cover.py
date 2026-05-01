"""Skills → agents (greedy weighted set cover with polyvalence bonus).

MVP_DESIGN §4.4:
    score(agent, K) = |skills(agent) ∩ K| · (1 + 0.05·polyvalence) · reputation
"""
from __future__ import annotations

from typing import Iterable

from src.db.client import get_db


def cover_skills_with_agents(
    skill_ids: Iterable[str], *, max_agents: int = 3
) -> list[dict]:
    """Return a list of agent docs (subset, ≤ max_agents) covering ``skill_ids``."""
    remaining: set[str] = set(skill_ids)
    if not remaining:
        return []

    db = get_db()
    candidates = list(db.agents.find(
        {"agent_id": {"$ne": "agent_synthetic_marshal"},
         "skill_ids": {"$in": list(remaining)}},
        {"_id": 0},
    ))
    chosen: list[dict] = []
    while remaining and candidates and len(chosen) < max_agents:
        def score(a: dict) -> float:
            cover = len(set(a["skill_ids"]) & remaining)
            return cover * (1.0 + 0.05 * a.get("polyvalence", len(a["skill_ids"]))) * a.get("reputation", 0.5)

        best = max(candidates, key=score)
        if score(best) <= 0:
            break
        chosen.append(best)
        remaining -= set(best["skill_ids"])
        candidates = [a for a in candidates if a["agent_id"] != best["agent_id"]]
    return chosen
