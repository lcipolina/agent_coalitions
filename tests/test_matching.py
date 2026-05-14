"""Sanity test for matching.search_skills (mock-mode embeddings)."""
"""
Sanity test for matching.search_skills (mock-mode embeddings).

This module tests that the skill search returns at least one hit with the required fields.

How to run:
    pytest tests/test_matching.py

This test can be run standalone with pytest, or as part of the full test suite.
"""
from src.db.matching import search_skills


def test_search_returns_hits():
    """Test that search_skills returns at least one hit with required fields."""
    hits = search_skills("structural steel design", limit=5)
    assert len(hits) >= 1
    assert all("skill_id" in h and "score" in h for h in hits)
