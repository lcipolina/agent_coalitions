"""MongoDB client singleton + collection name registry."""
from __future__ import annotations

from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database

from src.core.config import settings

# Per MVP_DESIGN.md §3 — note: spec text says "11 collections" but enumerates 13
# (skills, agents, runs, subtasks, assignments, coalition_messages,
#  subtask_outputs, design_specs, validation_results, cost_estimates,
#  artifacts, events, reputation_updates). We use all 13.
COLLECTIONS: tuple[str, ...] = (
    "skills",
    "agents",
    "runs",
    "subtasks",
    "assignments",
    "coalition_messages",
    "subtask_outputs",
    "design_specs",
    "validation_results",
    "cost_estimates",
    "artifacts",
    "events",
    "reputation_updates",
    "llm_cache",
)


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(settings.mongodb_uri, appname="agent-coalitions")


def get_db() -> Database:
    return get_client()[settings.mongodb_db]
