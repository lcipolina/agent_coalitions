"""Quick health check for the MongoDB Atlas cluster used by this app.

Usage:
    conda run -n coalitions --no-capture-output python scripts/check_mongo.py

Reads the same `MONGODB_URI` / `MONGODB_DB` your app does (via
`src.core.config.settings`) and prints, in this order:

  - the cluster host (no credentials),
  - the database name,
  - a `ping` admin command,
  - the list of collections,
  - row counts for `runs` and `skills`,
  - whether the Atlas Vector Search index `skills_embedding_vector` is
    listed on the `skills` collection.

Exit code is 0 on success, non-zero on any failure — handy for cron-ing
the cluster's liveness if you're worried about Atlas pausing free-tier
clusters after inactivity.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Make `src/` importable when this script is run directly (not via `-m`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from src.core.config import settings


def _redact(uri: str) -> str:
    return re.sub(r"://[^@]+@", "://USER:REDACTED@", uri)


def main() -> int:
    print(f"URI    : {_redact(settings.mongodb_uri)}")
    print(f"DB     : {settings.mongodb_db}")
    try:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
        ping = client.admin.command("ping")
        print(f"ping   : ok={ping.get('ok')}")
    except PyMongoError as exc:
        print(f"PING FAILED: {exc!r}", file=sys.stderr)
        return 1

    db = client[settings.mongodb_db]
    cols = sorted(db.list_collection_names())
    print(f"colls  : {len(cols)} -> {cols}")
    print(f"runs   : {db.runs.estimated_document_count()} documents")
    print(f"skills : {db.skills.estimated_document_count()} documents")

    # Atlas Vector Search index check (best-effort: requires Atlas, not local mongod).
    try:
        idx = list(db.skills.list_search_indexes())
        names = [i.get("name") for i in idx]
        ok = "skills_embedding_vector" in names
        print(f"vidx   : {'ok' if ok else 'MISSING'} (search indexes: {names})")
        if not ok:
            return 2
    except PyMongoError as exc:
        # Older pymongo / non-Atlas backends don't expose list_search_indexes.
        print(f"vidx   : skipped ({exc!r})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
