"""Idempotent index creation, including the Atlas Vector Search index on skills.embedding."""
from __future__ import annotations

import logging
from typing import Any

from pymongo import ASCENDING
from pymongo.database import Database
from pymongo.errors import OperationFailure

from src.db.client import COLLECTIONS, get_db

log = logging.getLogger(__name__)

VECTOR_INDEX_NAME = "skills_embedding_vector"
VECTOR_DIMENSIONS = 1536  # text-embedding-3-small


def ensure_collections(db: Database) -> None:
    """Create any missing collections from :data:`COLLECTIONS` (idempotent)."""
    existing = set(db.list_collection_names())
    for name in COLLECTIONS:
        if name not in existing:
            db.create_collection(name)


def ensure_regular_indexes(db: Database) -> None:
    """Create the regular B-tree indexes per MVP_DESIGN §3 (idempotent)."""
    db.skills.create_index([("category", ASCENDING)])
    db.skills.create_index([("weekly_installs", ASCENDING)])
    db.skills.create_index([("skill_id", ASCENDING)], unique=True)

    db.agents.create_index([("skill_ids", ASCENDING)])
    db.agents.create_index([("reputation", ASCENDING)])
    db.agents.create_index([("agent_id", ASCENDING)], unique=True)

    db.runs.create_index([("run_id", ASCENDING)], unique=True)

    db.subtasks.create_index([("run_id", ASCENDING), ("subtask_id", ASCENDING)])
    db.assignments.create_index([("run_id", ASCENDING), ("subtask_id", ASCENDING)])
    db.coalition_messages.create_index(
        [("run_id", ASCENDING), ("subtask_id", ASCENDING), ("ts", ASCENDING)]
    )
    db.subtask_outputs.create_index([("run_id", ASCENDING), ("subtask_id", ASCENDING)])
    db.design_specs.create_index([("run_id", ASCENDING)])
    db.validation_results.create_index([("run_id", ASCENDING)])
    db.cost_estimates.create_index([("run_id", ASCENDING)])
    db.artifacts.create_index([("run_id", ASCENDING)])
    db.events.create_index([("run_id", ASCENDING), ("ts", ASCENDING)])
    db.reputation_updates.create_index([("agent_id", ASCENDING)])
    db.reputation_updates.create_index([("run_id", ASCENDING)])


def ensure_vector_index(db: Database) -> bool:
    """Create Atlas Vector Search index on skills.embedding (idempotent).

    Returns True if the index now exists / was created, False if the cluster
    does not support Atlas Search (per Q14 we log a clear error and continue;
    callers may fall back to in-Python cosine for development, but G5 still
    requires this index).
    """
    spec: dict[str, Any] = {
        "name": VECTOR_INDEX_NAME,
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": VECTOR_DIMENSIONS,
                    "similarity": "cosine",
                }
            ]
        },
    }
    try:
        existing = list(db.skills.list_search_indexes())
        if any(idx.get("name") == VECTOR_INDEX_NAME for idx in existing):
            log.info("vector index %s already exists", VECTOR_INDEX_NAME)
            return True
        db.skills.create_search_index(spec)
        log.info("vector index %s submitted (Atlas may take ~1 min to build)", VECTOR_INDEX_NAME)
        return True
    except OperationFailure as e:
        log.error(
            "Atlas Search not available on this cluster — vector index NOT created. "
            "Per MVP_DESIGN.md §3.1, G5 requires this index. Error: %s",
            e,
        )
        return False


def ensure_all() -> dict[str, bool]:
    """Run all idempotent index/collection bootstrap steps; return a status dict."""
    db = get_db()
    ensure_collections(db)
    ensure_regular_indexes(db)
    vector_ok = ensure_vector_index(db)
    return {"vector_index": vector_ok}
