"""G3 self-check: connect to Mongo, ensure 13 collections + indexes, list them.

Usage:
    python -m src.scripts.ping_mongo
"""
from __future__ import annotations

import logging
import sys

from src.core.config import settings
from src.db.client import COLLECTIONS, get_db
from src.db.indexes import ensure_all


def main() -> int:
    """Ping Atlas, ensure all 13 collections + indexes exist, and report status."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db = get_db()
    # cheap round-trip
    db.command("ping")
    print(f"connected: db={settings.mongodb_db}")

    result = ensure_all()
    names = sorted(db.list_collection_names())
    print(f"collections ({len(names)}): {names}")

    missing = [c for c in COLLECTIONS if c not in names]
    if missing:
        print(f"MISSING collections: {missing}", file=sys.stderr)
        return 2

    print(f"vector index ok: {result['vector_index']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
