"""Agent-comms helpers — post / read / render coalition_messages rows.

This module is the team message bus: each subtask's coalition uses
``post`` and ``read`` to exchange ``coalition_messages`` rows during
the per-subtask execution loop. The MongoDB collection name
(``coalition_messages``) is preserved for backwards compatibility.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.db.client import get_db
from src.db.writes import log_event


def _now() -> datetime:
    """Return the current UTC timestamp.

    Returns:
        datetime: A timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


def post(
    run_id: str,
    subtask_id: str,
    sender: str,
    role: str,
    round_: int,
    text: str,
    meta: dict[str, Any] | None = None,
) -> None:
    """Insert one council message and emit a paired ``message_posted`` event.

    Args:
        run_id: Run identifier this message belongs to.
        subtask_id: Subtask identifier (e.g. ``"T3"``).
        sender: Agent id of the sender (``"agent_###"`` or marshal id).
        role: Role label for display (e.g. ``"agent"`` or ``"marshal"``).
        round_: Council round number (0 kickoff, 1 agents, 2 reconcile).
        text: Message body text.
        meta: Optional message metadata payload.

    Returns:
        None
    """
    db = get_db()
    db.coalition_messages.insert_one({
        "run_id": run_id,
        "subtask_id": subtask_id,
        "ts": _now(),
        "sender": sender,
        "role": role,
        "round": round_,
        "text": text,
        "meta": meta or {"type": None, "payload": {}},
    })
    log_event(run_id, "message_posted",
              {"subtask_id": subtask_id, "sender": sender, "round": round_})


def read(run_id: str, subtask_id: str, *, max_round: int | None = None) -> list[dict]:
    """Fetch council messages for a subtask, optionally capped by round.

    Args:
        run_id: Run identifier.
        subtask_id: Subtask identifier to filter messages.
        max_round: If provided, return messages with ``round <= max_round``.

    Returns:
        list[dict]: Messages sorted by timestamp ascending, with ``_id`` omitted.
    """
    q: dict[str, Any] = {"run_id": run_id, "subtask_id": subtask_id}
    if max_round is not None:
        q["round"] = {"$lte": max_round}
    return list(get_db().coalition_messages.find(q, {"_id": 0}).sort("ts", 1))


def render_log(run_id: str, subtask_id: str) -> str:
    """Render a subtask's full message log as a human-readable string.

    Args:
        run_id: Run identifier.
        subtask_id: Subtask identifier.

    Returns:
        str: Multi-line formatted log combining round, role, sender, and text.
    """
    rows = read(run_id, subtask_id)
    return "\n".join(
        f"[r{r['round']} {r['role']}:{r['sender']}] {r['text']}" for r in rows
    )
