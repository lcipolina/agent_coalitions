"""Sanity test for matching.search_skills (mock-mode embeddings)."""
from src.matching import search_skills


def test_search_returns_hits():
    hits = search_skills("structural steel design", limit=5)
    assert len(hits) >= 1
    assert all("skill_id" in h and "score" in h for h in hits)
