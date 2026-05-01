"""G5 self-check: run a vector search and print top hits.

Usage:
    python -m src.scripts.test_vector_search "structural steel design"
"""
from __future__ import annotations

import sys

from src.db.matching import search_skills


def main(argv: list[str] | None = None) -> int:
    """Run a single Atlas $vectorSearch query and print the top hits."""
    argv = argv if argv is not None else sys.argv[1:]
    query = argv[0] if argv else "structural steel design"
    hits = search_skills(query, limit=5)
    print(f"query: {query!r}")
    print(f"hits: {len(hits)}")
    for h in hits:
        print(f"  {h['score']:.4f}  {h['skill_id']:<40s} [{h.get('category')}]")
    return 0 if hits else 2


if __name__ == "__main__":
    sys.exit(main())
