"""Tests for coalitions.form_coalition."""
import numpy as np

from src.coalitions import CandidateSkill, coalition_value, form_coalition


def _mk(skill_id: str, cov: float, rep: float, installs: int, vec: list[float]):
    return CandidateSkill(
        skill_id=skill_id, name=skill_id, coverage=cov, prior_reputation=rep,
        weekly_installs=installs, embedding=np.asarray(vec, dtype=np.float32),
    )


def test_form_coalition_picks_highest_solo_first():
    candidates = [
        _mk("a", 0.9, 0.9, 1000, [1, 0, 0]),
        _mk("b", 0.2, 0.2, 100, [0, 1, 0]),
    ]
    coalition, _ = form_coalition(candidates)
    assert coalition[0].skill_id == "a"


def test_form_coalition_size_at_most_three():
    cands = [
        _mk(f"s{i}", 0.5, 0.5, 100, [1.0 if j == i else 0.0 for j in range(5)])
        for i in range(5)
    ]
    coalition, _ = form_coalition(cands)
    assert 1 <= len(coalition) <= 3


def test_complementarity_bonus_increases_value():
    a = _mk("a", 0.5, 0.5, 100, [1, 0, 0])
    b_orth = _mk("b", 0.5, 0.5, 100, [0, 1, 0])
    b_par = _mk("c", 0.5, 0.5, 100, [1, 0, 0])
    # populate solo via form_coalition (which sets it).
    form_coalition([a, b_orth, b_par])
    v_orth = coalition_value([a, b_orth])
    v_par = coalition_value([a, b_par])
    assert v_orth > v_par
