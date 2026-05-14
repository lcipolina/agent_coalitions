"""
Tests for coalitions.form_coalition.

This module tests coalition formation logic, including candidate selection, coalition size,
and complementarity bonus. It ensures the coalition logic is correct and robust.

How to run:
    pytest tests/test_coalitions.py

This test can be run standalone with pytest, or as part of the full test suite.
"""
"""Tests for coalitions.form_coalition."""
import numpy as np

from src.agents.coalitions import CandidateSkill, coalition_value, form_coalition


def _mk(skill_id: str, cov: float, rep: float, installs: int, vec: list[float]):
    """Helper to create a CandidateSkill for testing.

    Args:
        skill_id (str): Skill identifier.
        cov (float): Coverage value.
        rep (float): Reputation value.
        installs (int): Weekly installs.
        vec (list[float]): Embedding vector.

    Returns:
        CandidateSkill: Candidate skill instance.
    """
    return CandidateSkill(
        skill_id=skill_id, name=skill_id, coverage=cov, prior_reputation=rep,
        weekly_installs=installs, embedding=np.asarray(vec, dtype=np.float32),
    )


def test_form_coalition_picks_highest_solo_first():
    """Test that the coalition picks the highest solo value candidate first."""
    candidates = [
        _mk("a", 0.9, 0.9, 1000, [1, 0, 0]),
        _mk("b", 0.2, 0.2, 100, [0, 1, 0]),
    ]
    coalition, _ = form_coalition(candidates)
    assert coalition[0].skill_id == "a"


def test_form_coalition_size_at_most_three():
    """Test that the coalition size is at most three."""
    cands = [
        _mk(f"s{i}", 0.5, 0.5, 100, [1.0 if j == i else 0.0 for j in range(5)])
        for i in range(5)
    ]
    coalition, _ = form_coalition(cands)
    assert 1 <= len(coalition) <= 3


def test_complementarity_bonus_increases_value():
    """Test that complementarity bonus increases coalition value for orthogonal skills."""
    a = _mk("a", 0.5, 0.5, 100, [1, 0, 0])
    b_orth = _mk("b", 0.5, 0.5, 100, [0, 1, 0])
    b_par = _mk("c", 0.5, 0.5, 100, [1, 0, 0])
    # populate solo via form_coalition (which sets it).
    form_coalition([a, b_orth, b_par])
    v_orth = coalition_value([a, b_orth])
    v_par = coalition_value([a, b_par])
    assert v_orth > v_par
