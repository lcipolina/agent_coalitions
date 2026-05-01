"""Blackboard helpers — post / read / render coalition_messages rows."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.db.client import get_db
from src.db.writes import log_event


def _now() -> datetime:
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
    """Insert a single coalition message and emit a paired ``message_posted`` event."""
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
    """Return coalition messages for one subtask, optionally capped at ``max_round``."""
    q: dict[str, Any] = {"run_id": run_id, "subtask_id": subtask_id}
    if max_round is not None:
        q["round"] = {"$lte": max_round}
    return list(get_db().coalition_messages.find(q, {"_id": 0}).sort("ts", 1))


def render_log(run_id: str, subtask_id: str) -> str:
    """Render the full message log for a subtask as a single human-readable string."""
    rows = read(run_id, subtask_id)
    return "\n".join(
        f"[r{r['round']} {r['role']}:{r['sender']}] {r['text']}" for r in rows
    )
