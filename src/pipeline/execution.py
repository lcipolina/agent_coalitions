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
from src.agents.coalitions import CandidateSkill, form_coalition
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
    return list(seen.values())[:15]


def execute_subtask(run_id: str, subtask: dict, upstream_outputs: list[dict]) -> dict:
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
    agents = cover_skills_with_agents(coalition_skill_ids, max_agents=3)
    coalition_agent_ids = [a["agent_id"] for a in agents] or [MARSHAL_ID]

    contribution_scores = []
    covered: set[str] = set()
    for a, c in zip(agents, coalition):
        contributed = sorted(set(a["skill_ids"]) & set(coalition_skill_ids) - covered)
        covered.update(contributed)
        contribution_scores.append({
            "agent_id": a["agent_id"],
            "score": float(c.solo),
            "skills_contributed": contributed,
        })

    emit("coalition_formed", {
        "subtask_id": subtask["subtask_id"],
        "skills": [
            {"skill_id": c.skill_id, "name": c.name, "solo": float(c.solo)}
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
    kickoff_text = kickoff(run_id, subtask, coalition_agent_ids, upstream_outputs)
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
