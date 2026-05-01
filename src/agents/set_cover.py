"""Skills → agents (greedy weighted set cover with polyvalence bonus).

WHAT THIS FILE DOES (in plain English)
--------------------------------------
After the marshal has chosen a *set of skills* the team needs (e.g.
``{aerodynamics-and-cfd, propulsion-systems, composite-materials}``),
we still need to pick the **actual agents** that will deliver those
skills. Each agent in MongoDB carries a small list of ``skill_ids``,
so this is the classic *Set Cover* problem:

    Given a target set of skills K, pick the smallest possible group
    of agents whose combined skills cover K.

Set Cover is NP-hard in general, but the **greedy** algorithm
(repeatedly pick the agent that covers the most still-uncovered
skills) is the textbook approximation: it is provably within a
``ln |K|`` factor of optimal and is what we use here.

We weight the greedy pick with two extra factors so we don't just
maximise raw skill count:

  * ``(1 + 0.05 · polyvalence)`` \u2014 a tiny bonus for generalist agents
    that carry many skills overall (proxy for adaptability).
  * ``reputation`` \u2014 multiply by the agent's running reputation in
    [0, 1] so agents with a track record are preferred when there is
    a tie on coverage.

This file is referenced by MVP_DESIGN \u00a74.4. The exact weighting:

    score(agent, K) = |skills(agent) \u2229 K|
                    \u00b7 (1 + 0.05 \u00b7 polyvalence)
                    \u00b7 reputation
"""
from __future__ import annotations

from typing import Iterable

from src.db.client import get_db


def cover_skills_with_agents(
    skill_ids: Iterable[str], *, max_agents: int = 3
) -> list[dict]:
    """Pick a small group of agents that together cover ``skill_ids``.

    Parameters
    ----------
    skill_ids :
        The skills the team needs (chosen earlier by the marshal /
        coalition-formation step).
    max_agents :
        Hard upper bound on team size. The greedy loop stops as soon
        as either every skill is covered, no candidate adds new
        coverage, or this many agents have been picked. Default is 3
        so teams stay small and Shapley contribution remains readable
        in the UI.

    Returns
    -------
    list of agent documents (raw Mongo dicts, ``_id`` removed) in the
    order they were greedily picked. May be shorter than the number of
    requested skills if a single polyvalent agent covers several at
    once.
    """
    # ``remaining`` is the set of skills still uncovered. We mutate it
    # as we pick agents \u2014 once it's empty we're done.
    remaining: set[str] = set(skill_ids)
    if not remaining:
        return []

    db = get_db()

    # Pre-filter the agent pool to *only* those who carry at least one
    # of the requested skills. This is a cheap Mongo-side prune that
    # keeps the Python-side scoring loop short. We also drop the
    # marshal agent \u2014 it's a synthetic fallback "everyone-does-
    # everything" agent (see MVP_DESIGN \u00a73.5) and would always score
    # highest, defeating the whole point of forming a real team.
    candidates = list(db.agents.find(
        {"agent_id": {"$ne": "agent_marshal"},
         "skill_ids": {"$in": list(remaining)}},
        {"_id": 0},
    ))

    chosen: list[dict] = []

    # Classic greedy set-cover loop. Stops when:
    #   - every requested skill is covered (``remaining`` empty), OR
    #   - no candidate can contribute new coverage (``score == 0``), OR
    #   - we've hit the team-size budget (``max_agents``).
    while remaining and candidates and len(chosen) < max_agents:
        def score(a: dict) -> float:
            # How many of the *still-uncovered* skills this agent has.
            # This is the only term that decreases between iterations
            # \u2014 the bonus / reputation factors are constants per agent.
            cover = len(set(a["skill_ids"]) & remaining)
            # Polyvalence bonus: agents with a wider skill repertoire
            # break ties by being slightly preferred. The 0.05
            # coefficient is small on purpose \u2014 we don't want it to
            # dominate raw coverage.
            polyvalence = a.get("polyvalence", len(a["skill_ids"]))
            # Reputation lives in [0, 1]; agents with no history fall
            # back to a neutral 0.5 so they aren't permanently locked
            # out of selection on cold start.
            reputation = a.get("reputation", 0.5)
            return cover * (1.0 + 0.05 * polyvalence) * reputation

        # Pick the highest-scoring candidate this round.
        best = max(candidates, key=score)

        # Defensive stop: if even the best candidate adds zero new
        # coverage, no further agent will help \u2014 bail out and let the
        # caller decide what to do with any leftover ``remaining``
        # skills (typically: fall back to the marshal).
        if score(best) <= 0:
            break

        chosen.append(best)
        # Remove all of ``best``'s skills from the open set, even
        # those that weren't in ``remaining`` to start with \u2014 a
        # no-op for them, but keeps the math clean.
        remaining -= set(best["skill_ids"])
        # And remove ``best`` from the candidate pool so we don't
        # pick the same agent twice.
        candidates = [a for a in candidates if a["agent_id"] != best["agent_id"]]
    return chosen
