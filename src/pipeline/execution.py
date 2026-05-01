"""Per-subtask execution loop: assign coalition, run blackboard rounds,
write subtask_outputs.

Per Amendment 3.9: agents post in parallel in round 1 (each sees only the
marshal kickoff and upstream summaries). Round 2 = marshal reconcile.
At most one revision round (3) — omitted in mock for simplicity.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from src.agents.blackboard import post
from src.agents.coalitions import CandidateSkill, form_coalition, shapley_values
from src.db.client import get_db
from src.db.writes import insert_with_event, log_event
from src.llm.openai_client import chat, embed
from src.llm.prompts import render
from src.agents.marshal import MARSHAL_ID, kickoff, reconcile
from src.db.matching import search_skills
from src.agents.set_cover import cover_skills_with_agents
from src.core.progress import emit
from src.core.tokens import truncate_to_tokens


def _candidates_for(subtask: dict) -> list[CandidateSkill]:
    db = get_db()
    seen: dict[str, CandidateSkill] = {}
    # Embed once per capability.
    qvec_cache: dict[str, np.ndarray] = {}
    for cap in subtask.get("required_capabilities", []):
        qvec = np.asarray(embed(cap), dtype=np.float32)
        qvec_cache[cap] = qvec
        hits = search_skills(cap, limit=8)
        for h in hits:
            if h["skill_id"] in seen:
                continue
            full = db.skills.find_one(
                {"skill_id": h["skill_id"]},
                {"_id": 0, "skill_id": 1, "name": 1, "weekly_installs": 1,
                 "prior_reputation": 1, "embedding": 1},
            )
            if not full:
                continue
            e = np.asarray(full["embedding"], dtype=np.float32)
            cov = float(np.clip(
                np.dot(qvec, e) / (np.linalg.norm(qvec) * np.linalg.norm(e) + 1e-12),
                0.0, 1.0,
            ))
            seen[full["skill_id"]] = CandidateSkill(
                skill_id=full["skill_id"],
                name=full["name"],
                coverage=cov,
                prior_reputation=full.get("prior_reputation", 0.5),
                weekly_installs=full.get("weekly_installs", 0),
                embedding=e,
            )
    log_event(
        run_id=subtask["run_id"],
        kind="skill_search",
        payload={"subtask_id": subtask["subtask_id"], "n_candidates": len(seen)},
    )
    # Coverage floor: drop any candidate whose semantic similarity to the
    # subtask query is below 0.30. Without this filter, a skill with a
    # great prior_reputation/install count but a poor semantic match (e.g.
    # ``propulsion-systems`` for a bridge subtask) can still slip into the
    # team because β·prior_rep + γ·log(installs) compensates for the low
    # α·coverage term. The floor enforces "must be at least loosely
    # on-topic" before rep/installs get a vote.
    COVERAGE_FLOOR = 0.30
    filtered = [c for c in seen.values() if c.coverage >= COVERAGE_FLOOR]
    # If the floor wipes out the candidate set entirely (very off-domain
    # subtask), fall back to the top-k by coverage so the pipeline still
    # makes progress instead of crashing.
    if not filtered:
        filtered = sorted(seen.values(), key=lambda c: c.coverage, reverse=True)[:5]
    return filtered[:15]


def execute_subtask(run_id: str, subtask: dict, upstream_outputs: list[dict],
                    criteria: list[dict] | None = None) -> dict:
    """Run the full per-subtask loop and return the persisted output doc.

    Pipeline:
      1. retrieve candidate skills via vector search
      2. form a coalition of skills + cover them with agents
      3. round 0 marshal kickoff → round 1 agents → round 2 marshal reconcile
      4. write the assignment, blackboard messages and ``subtask_outputs`` row
    """
    db = get_db()
    db.subtasks.update_one(
        {"run_id": run_id, "subtask_id": subtask["subtask_id"]},
        {"$set": {"status": "in_progress"}},
    )

    candidates = _candidates_for(subtask)
    emit("candidates_found", {
        "subtask_id": subtask["subtask_id"], "n": len(candidates),
    })
    coalition, rationale = form_coalition(candidates)
    coalition_skill_ids = [c.skill_id for c in coalition]
    solo_by_skill = {c.skill_id: float(c.solo) for c in coalition}
    # Exact Shapley value per skill in the chosen team (induced-subgraph
    # closed form: φ_i = a_i + ½·Σ w_ij). O(k²), k≤3, so essentially free.
    shapley_by_skill = shapley_values(coalition)
    agents = cover_skills_with_agents(coalition_skill_ids, max_agents=3)
    coalition_agent_ids = [a["agent_id"] for a in agents] or [MARSHAL_ID]

    # Build the per-agent contribution table by iterating over the agents
    # the set-cover step actually returned. Each agent gets the slice of the
    # coalition's skills it can supply (minus skills already claimed by an
    # earlier agent). The agent's `score` is the sum of solo values for
    # those skills; `shapley` is the sum of exact Shapley values for the
    # same skills (fair-credit share that accounts for complementarity
    # with the rest of the team).
    contribution_scores = []
    covered: set[str] = set()
    for a in agents:
        contributed = sorted(
            (set(a["skill_ids"]) & set(coalition_skill_ids)) - covered
        )
        covered.update(contributed)
        score = sum(solo_by_skill.get(s, 0.0) for s in contributed)
        shap = sum(shapley_by_skill.get(s, 0.0) for s in contributed)
        contribution_scores.append({
            "agent_id": a["agent_id"],
            "score": float(score),
            "shapley": float(shap),
            "skills_contributed": contributed,
        })

    emit("coalition_formed", {
        "subtask_id": subtask["subtask_id"],
        "skills": [
            {"skill_id": c.skill_id, "name": c.name,
             "solo": float(c.solo),
             "shapley": float(shapley_by_skill.get(c.skill_id, 0.0))}
            for c in coalition
        ],
        "agents": contribution_scores,
        "rationale": rationale,
    })

    # Persist assignment.
    insert_with_event(
        "assignments",
        {
            "run_id": run_id,
            "subtask_id": subtask["subtask_id"],
            "coalition_skill_ids": coalition_skill_ids,
            "coalition_agent_ids": coalition_agent_ids,
            "marshal_agent_id": MARSHAL_ID,
            "contribution_scores": contribution_scores,
            "selection_rationale": rationale,
        },
        event_kind="coalition_formed",
        event_payload={"subtask_id": subtask["subtask_id"],
                       "skills": coalition_skill_ids,
                       "agents": coalition_agent_ids},
    )

    # Round 0: marshal kickoff.
    kickoff_text = kickoff(run_id, subtask, coalition_agent_ids, upstream_outputs,
                           criteria=criteria)
    emit("round_posted", {"subtask_id": subtask["subtask_id"],
                          "round": 0, "sender": MARSHAL_ID})

    # Round 1: agents contribute (mock = "in parallel"; serial calls but no
    # cross-visibility — each agent only sees kickoff + upstream summaries).
    agent_skills_by_id = {a["agent_id"]: a.get("skill_ids", []) for a in agents}
    for aid in coalition_agent_ids:
        if aid == MARSHAL_ID:
            continue
        agent_prompt = render(
            "agent",
            agent_id=aid,
            subtask=subtask,
            skills=agent_skills_by_id.get(aid, []),
            kickoff_text=kickoff_text,
            upstream_summaries=upstream_outputs,
        )
        text = chat(
            agent_prompt,
            role="agent", agent_id=aid, subtask_id=subtask["subtask_id"],
        )
        post(run_id, subtask["subtask_id"], aid, "agent", 1, text)
        emit("round_posted", {"subtask_id": subtask["subtask_id"],
                              "round": 1, "sender": aid})

    # Round 2: marshal reconcile → subtask_outputs.
    reconciled = reconcile(run_id, subtask)
    emit("round_posted", {"subtask_id": subtask["subtask_id"],
                          "round": 2, "sender": MARSHAL_ID})
    summary = truncate_to_tokens(reconciled, 200)

    structured: dict[str, Any] = {}
    output_doc = {
        "run_id": run_id,
        "subtask_id": subtask["subtask_id"],
        "summary": summary,
        "structured": structured,
    }
    insert_with_event(
        "subtask_outputs", output_doc,
        event_kind="subtask_completed",
        event_payload={"subtask_id": subtask["subtask_id"],
                       "summary_chars": len(summary)},
    )
    db.subtasks.update_one(
        {"run_id": run_id, "subtask_id": subtask["subtask_id"]},
        {"$set": {"status": "complete"}},
    )
    return output_doc
