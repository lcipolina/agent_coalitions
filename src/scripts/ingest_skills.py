"""G4 self-check: ingest skills_seed.json and synthesise 21 agents.

Usage:
    python -m src.scripts.ingest_skills [--drop]
"""
from __future__ import annotations

import argparse
import sys

from src.db.client import get_db
from src.db.indexes import ensure_all
from src.db.seed import seed_agents, seed_skills


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ensure indexes, then seed skills + agents."""
    p = argparse.ArgumentParser()
    p.add_argument("--drop", action="store_true",
                   help="delete existing skills/agents before seeding")
    args = p.parse_args(argv)

    ensure_all()  # idempotent
    n_skills = seed_skills(drop=args.drop)
    n_agents = seed_agents(drop=args.drop)

    db = get_db()
    db_skills = db.skills.count_documents({})
    db_agents = db.agents.count_documents({})
    print(f"seeded skills: {n_skills}  (collection now has {db_skills})")
    print(f"seeded agents: {n_agents}  (collection now has {db_agents}, "
          f"includes 1 synthetic marshal)")

    # MVP_DESIGN amendment §3.13: 20 agents + 1 marshal = 21.
    if db_agents != 21:
        print(f"WARNING: expected 21 agents (20 + marshal), got {db_agents}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
