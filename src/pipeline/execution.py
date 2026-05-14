"""Per-subtask execution loop: assign coalition, run agent-comms rounds,
write subtask_outputs.

Per Amendment 3.9: agents post in parallel in round 1 (each sees only the
marshal kickoff and upstream summaries). Round 2 = marshal reconcile.
At most one revision round (3) — omitted in mock for simplicity.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from src.agents.agent_comms import post
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


# ---------------------------------------------------------------------------
# Prompt-domain filter
# ---------------------------------------------------------------------------
# Vector search alone cannot reliably keep an aerospace propulsion skill
# out of a bridge subtask: generic engineering vocabulary ("loads",
# "dynamics", "materials") creates near-uniform cosine similarity across
# domains, and in mock mode the embeddings are SHA-256 hashes — random.
# So we add an explicit, tag-driven domain *allow-list* on top of the
# coverage floor. A skill is kept only if its tags intersect the
# in-domain set OR its skill_id is in a small set of domain-agnostic
# helpers (technical writing, project management, etc.).

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bridge":     ("bridge", "viaduct", "overpass", "footbridge", "span"),
    "building":   ("building", "tower", "skyscraper", "office", "residential"),
    "aircraft":   ("aircraft", "airplane", "drone", "uav", "satellite"),
    "rover":      ("rover", "robot", "agv", "amr", "autonomous vehicle"),
    "vehicle":    ("car ", "truck ", " ev ", "electric vehicle", "chassis"),
    "ship":       ("ship", "vessel", "boat", "marine", "hull"),
}

_IN_DOMAIN_TAGS: dict[str, frozenset[str]] = {
    "bridge": frozenset({
        "civil", "bridge", "structural", "concrete", "rebar", "steel",
        "geotechnical", "loads", "seismic", "wind", "fatigue", "aeroelastic",
        "eurocode", "aashto", "hl-93", "deck", "pier", "abutment",
        "cable-stayed", "suspension", "truss", "arch",
        "elevation", "rendering", "aesthetic", "lighting", "color", "palette",
        "pedestrian", "cyclist",
        "cost", "qto", "lifecycle", "carbon", "environmental",
        "traffic", "hydrology", "river", "site", "geometry", "alignment",
        "constructability", "fea", "validation", "materials",
    }),
}

# Skill IDs that are domain-agnostic enough to allow under any domain
# (writing, applied math, generic management). Keeps technical-writing
# from being filtered out of a bridge brief.
_DOMAIN_AGNOSTIC_SKILL_IDS: frozenset[str] = frozenset({
    "technical-writing", "executive-summary-drafting", "risk-register-authoring",
    "applied-mathematics", "project-management",
    "regulatory-compliance", "safety-and-reliability", "systems-engineering",
    "sustainability", "human-factors",
})


def _detect_domain(prompt: str) -> str | None:
    p = (prompt or "").lower()
    for domain, kws in _DOMAIN_KEYWORDS.items():
        if any(kw in p for kw in kws):
            return domain
    return None


def _is_in_domain(
    skill_id: str, tags: list[str] | None, domain: str | None,
) -> bool:
    """Return True if a skill is acceptable for the detected domain.

    Unknown domain -> always accept (no filter).
    Known domain   -> accept iff skill_id is domain-agnostic OR tags
                      intersect the in-domain tag set.
    """
    if not domain:
        return True
    if skill_id in _DOMAIN_AGNOSTIC_SKILL_IDS:
        return True
    in_tags = _IN_DOMAIN_TAGS.get(domain)
    if not in_tags:
        return True  # domain registered but no tag list yet; permissive.
    if not tags:
        return False
    return any(t in in_tags for t in tags)


def _in_domain_fallback_candidates(
    domain: str, qvec: np.ndarray, limit: int = 8,
) -> list[dict]:
    """Catalog scan returning skills tagged as in-domain.

    Used when vector search + the domain filter wipe out the candidate
    set entirely (mock mode with random embeddings, or a pathological
    capability string). Cosine is computed against the supplied query
    vector to give the coverage score a meaningful number.
    """
    db = get_db()
    in_tags = _IN_DOMAIN_TAGS.get(domain)
    if not in_tags:
        return []
    rows = list(db.skills.find(
        {"tags": {"$in": list(in_tags)}},
        {"_id": 0, "skill_id": 1, "name": 1, "weekly_installs": 1,
         "prior_reputation": 1, "embedding": 1, "tags": 1},
    ))
    if not rows:
        return []
    qn = qvec / max(float(np.linalg.norm(qvec)), 1e-12)
    for r in rows:
        e = np.asarray(r["embedding"], dtype=np.float32)
        en = e / max(float(np.linalg.norm(e)), 1e-12)
        r["_cov"] = float(np.clip(np.dot(qn, en), 0.0, 1.0))
    rows.sort(
        key=lambda r: (r.get("prior_reputation", 0.5), r["_cov"]),
        reverse=True,
    )
    return rows[:limit]


def _candidates_for(subtask: dict) -> list[CandidateSkill]:
    db = get_db()
    seen: dict[str, CandidateSkill] = {}
    # Anchor every capability query with the run's original prompt so the
    # vector match is biased toward the actual project domain ("design a
    # bridge for 50 cars" + "material strength under cyclic load") rather
    # than the generic engineering vocabulary in the capability alone. This
    # is what stops e.g. ``propulsion-systems`` matching bridge subtasks
    # purely because both are nominally "engineering" text.
    run_doc = db.runs.find_one(
        {"run_id": subtask["run_id"]}, {"_id": 0, "prompt": 1},
    ) or {}
    prompt_anchor = (run_doc.get("prompt") or "").strip()
    domain = _detect_domain(prompt_anchor)
    # Embed once per (anchored) capability.
    qvec_cache: dict[str, np.ndarray] = {}
    for cap in subtask.get("required_capabilities", []):
        anchored = f"{prompt_anchor}\n{cap}" if prompt_anchor else cap
        qvec = np.asarray(embed(anchored), dtype=np.float32)
        qvec_cache[cap] = qvec
        # Atlas Vector Search retrieval still uses just the capability
        # so the recall set is broad; the *coverage* score and the floor
        # below are what enforce domain alignment.
        hits = search_skills(cap, limit=8)
        for h in hits:
            if h["skill_id"] in seen:
                continue
            full = db.skills.find_one(
                {"skill_id": h["skill_id"]},
                {"_id": 0, "skill_id": 1, "name": 1, "weekly_installs": 1,
                 "prior_reputation": 1, "embedding": 1, "tags": 1},
            )
            if not full:
                continue
            # Drop skills whose tags don't intersect the in-domain set
            # for the detected project domain. This is the second gate
            # after the coverage floor below; together they keep e.g.
            # propulsion or PCB-design skills out of a bridge brief.
            if not _is_in_domain(full["skill_id"], full.get("tags"), domain):
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
    # In-domain fallback: vector search + the off-domain filter can wipe
    # out the candidate set when (a) the prompt is highly specific and
    # the LLM-decomposed capability is generic, or (b) the run is in
    # mock mode where embeddings are SHA-256 hashes (effectively random).
    # In either case, pull a small in-domain candidate set straight from
    # the catalog so the pipeline produces sensible team picks instead
    # of crashing or selecting whatever weak match happens to survive.
    if domain and len(seen) < 3:
        any_qvec = next(iter(qvec_cache.values()), None)
        if any_qvec is None:
            any_qvec = np.asarray(embed(prompt_anchor or domain), dtype=np.float32)
        for full in _in_domain_fallback_candidates(domain, any_qvec, limit=8):
            sid = full["skill_id"]
            if sid in seen:
                continue
            e = np.asarray(full["embedding"], dtype=np.float32)
            seen[sid] = CandidateSkill(
                skill_id=sid,
                name=full["name"],
                coverage=float(full.get("_cov", 0.5)),
                prior_reputation=full.get("prior_reputation", 0.5),
                weekly_installs=full.get("weekly_installs", 0),
                embedding=e,
            )
    # Coverage floor: drop any candidate whose semantic similarity to the
    # *prompt-anchored* capability query is below 0.40. The anchor
    # concatenates the run prompt to each capability before embedding, so
    # an off-domain skill (e.g. ``propulsion-systems``) needs to match
    # *both* the project subject (a bridge) and the capability (cyclic
    # loads) to clear the floor — which it won't.
    COVERAGE_FLOOR = 0.40
    filtered = [c for c in seen.values() if c.coverage >= COVERAGE_FLOOR]
    # If the floor wipes out the candidate set entirely (very off-domain
    # subtask, or mock mode random embeddings), fall back to the top-k by
    # coverage so the pipeline still makes progress instead of crashing.
    if not filtered:
        filtered = sorted(seen.values(), key=lambda c: c.coverage, reverse=True)[:5]
    return filtered[:15]


def execute_subtask(run_id: str, subtask: dict, upstream_outputs: list[dict],
                                        criteria: list[dict] | None = None) -> dict:
        """Run the per-subtask execution loop and persist its artifacts.

        Steps:
            1. Retrieve candidate skills via vector search
            2. Form a coalition of skills and cover them with agents
            3. Round 0 marshal kickoff → Round 1 agents → Round 2 marshal reconcile
            4. Write the assignment, council messages, and ``subtask_outputs`` row

        Args:
                run_id: The active run identifier.
                subtask: The subtask document (id/title/deps) to execute.
                upstream_outputs: Summaries from upstream subtasks for context.
                criteria: Optional acceptance-criteria list for the kickoff.

        Returns:
                dict: The persisted ``subtask_outputs`` document.
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
