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
)


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    # Short timeouts so a DNS / network failure surfaces in ~5s instead of the
    # pymongo default 20s+ — important for demos on flaky Wi-Fi where we want
    # a clear error banner, not a frozen UI.
    return MongoClient(
        settings.mongodb_uri,
        appname="agent-coalitions",
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )


def get_db() -> Database:
    return get_client()[settings.mongodb_db]


def ping_db(timeout_ms: int = 3000) -> tuple[bool, str | None]:
    """Best-effort connectivity check. Returns ``(ok, error_message)``.

    Used by the Streamlit entry point to show a friendly banner instead of a
    raw stack trace when DNS / Atlas is unreachable.
    """
    try:
        client = MongoClient(
            settings.mongodb_uri,
            appname="agent-coalitions-ping",
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
        )
        client.admin.command("ping")
        return True, None
    except Exception as exc:  # noqa: BLE001 — we want every failure mode
        return False, f"{type(exc).__name__}: {exc}"
