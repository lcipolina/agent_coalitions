"""Stage-2: pairwise-complementarity coalition formation (rank-1 Shapley).

See MVP_DESIGN §4.3.

Solo value:
    v({s}) = α·coverage(s,q) + β·prior_reputation(s) + γ·log(1+installs(s))
with α=0.6, β=0.3, γ=0.1 (γ pre-normalised by max log-installs in the
candidate set so it is in [0,1]).

Pairwise value:
    v({s_i, s_j}) = v({s_i}) + v({s_j}) + λ·(1 - cos(e_i, e_j))
with λ=0.4.

Greedy: start from argmax v({s}); add marginal-best skill while marginal
contribution ≥ τ=0.05 and |coalition| < 3.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

ALPHA = 0.6
BETA = 0.3
GAMMA = 0.1
LAMBDA = 0.4
TAU = 0.05
MAX_COALITION = 3


@dataclass
class CandidateSkill:
    """One candidate skill considered for coalition formation.

    Attributes:
        skill_id: Stable identifier for the skill in the catalog.
        name: Human-readable skill name.
        coverage: Cosine similarity to the subtask query, clipped to [0, 1].
        prior_reputation: Prior reputation score carried across runs.
        weekly_installs: Proxy for adoption/popularity of the skill.
        embedding: Vector embedding for pairwise complementarity.
        solo: Precomputed solo value ``v({s})`` used in coalition scoring.
        skills_contributed: Labels of concrete skills this item supplies.
    """

    skill_id: str
    name: str
    coverage: float                  # cosine(e_skill, e_q) clipped [0,1]
    prior_reputation: float
    weekly_installs: int
    embedding: np.ndarray
    solo: float = 0.0
    skills_contributed: list[str] = field(default_factory=list)


def _solo_value(c: CandidateSkill, gamma_norm: float) -> float:
    """Compute the solo value for a single candidate skill.

    Args:
        c: The candidate skill.
        gamma_norm: Normalisation term for the log-installs component.

    Returns:
        float: The solo value ``α·coverage + β·prior + γ·log(1+installs)/norm``.
    """
    return (
        ALPHA * c.coverage
        + BETA * c.prior_reputation
        + GAMMA * (math.log(1 + c.weekly_installs) / gamma_norm)
    )


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors (safe on zero vectors)."""
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def coalition_value(coalition: Sequence[CandidateSkill]) -> float:
    """Pairwise-additive value of a coalition (rank-1 Shapley approximation)."""
    if not coalition:
        return 0.0
    total = sum(c.solo for c in coalition)
    for i in range(len(coalition)):
        for j in range(i + 1, len(coalition)):
            total += LAMBDA * (1.0 - _cos(coalition[i].embedding, coalition[j].embedding))
    return total


def shapley_values(coalition: Sequence[CandidateSkill]) -> dict[str, float]:
    """Exact Shapley value for the induced-subgraph game (Deng-Papadimitriou).

    For ``v(S) = Σ_{i∈S} a_i + Σ_{i<j, i,j∈S} w_ij`` the Shapley value of
    player ``i`` collapses to the closed form

        φ_i  =  a_i  +  ½ · Σ_{j ≠ i} w_ij

    with ``a_i = c.solo`` and ``w_ij = λ · (1 − cos(e_i, e_j))``. O(k²) for
    coalition size ``k`` — trivial cost compared to any LLM call.
    """
    out: dict[str, float] = {}
    n = len(coalition)
    for i in range(n):
        ci = coalition[i]
        edge_sum = 0.0
        for j in range(n):
            if i == j:
                continue
            edge_sum += LAMBDA * (1.0 - _cos(ci.embedding, coalition[j].embedding))
        out[ci.skill_id] = float(ci.solo + 0.5 * edge_sum)
    return out


def form_coalition(
    candidates: list[CandidateSkill],
    *,
    max_size: int = MAX_COALITION,
    tau: float = TAU,
) -> tuple[list[CandidateSkill], str]:
    """Greedily build a coalition of up to ``max_size`` skills.

    Seeded by the highest solo-value skill, then iteratively adds the
    candidate with the largest marginal contribution to ``coalition_value``
    until either ``max_size`` is hit or the best marginal falls below
    ``tau``. Returns the chosen coalition plus a short rationale string
    describing each pick (used in the UI / persisted to assignments).
    """
    if not candidates:
        return [], "no candidates"

    # Pre-normalise the γ-installs term so its contribution lies in [0,1]
    # regardless of the largest weekly_installs value in the candidate set.
    # Pre-normalise gamma so γ-term ∈ [0,1].
    max_log = max(math.log(1 + c.weekly_installs) for c in candidates) or 1.0
    for c in candidates:
        c.solo = _solo_value(c, gamma_norm=max_log)

    coalition = [max(candidates, key=lambda c: c.solo)]
    base_v = coalition_value(coalition)
    rationale_parts = [
        f"Seed: {coalition[0].skill_id} (solo={coalition[0].solo:.3f})."
    ]

    # ----- Greedy growth loop -----
    # At each step, score every remaining candidate by the marginal value
    # it would add to the current coalition, and pick the best — provided
    # the marginal exceeds τ. Stops early on a weak marginal so we don't
    # pad the coalition with low-signal skills.
    pool = [c for c in candidates if c.skill_id != coalition[0].skill_id]
    while len(coalition) < max_size and pool:
        best, best_marginal = None, -1.0
        for c in pool:
            v_new = coalition_value([*coalition, c])
            marginal = v_new - base_v
            if marginal > best_marginal:
                best, best_marginal = c, marginal
        if best is None or best_marginal < tau:
            rationale_parts.append(
                f"Stop: best marginal {best_marginal:.3f} < τ={tau}."
            )
            break
        coalition.append(best)
        base_v = coalition_value(coalition)
        pool = [c for c in pool if c.skill_id != best.skill_id]
        rationale_parts.append(
            f"+{best.skill_id} (marginal={best_marginal:.3f})."
        )

    return coalition, " ".join(rationale_parts)
