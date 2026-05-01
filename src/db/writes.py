"""Write helpers that auto-emit a row in `events` for traceability.

Per MVP_DESIGN.md §9.4 G6: every pipeline stage must write ≥1 events row.
The convention: when a writer inserts a domain doc, also insert a paired
events row describing the stage.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from src.db.client import get_db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def log_event(
    run_id: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    db: Database | None = None,
) -> None:
    (db or get_db()).events.insert_one(
        {"run_id": run_id, "ts": _now(), "kind": kind, "payload": payload or {}}
    )


def insert_with_event(
    collection: str,
    doc: dict[str, Any],
    *,
    event_kind: str,
    event_payload: dict[str, Any] | None = None,
    db: Database | None = None,
) -> Any:
    """Insert *doc* into *collection* and emit a paired events row.

    *doc* must contain a ``run_id`` field.
    """
    db = db or get_db()
    if "run_id" not in doc:
        raise ValueError("doc must contain run_id for traceability")
    res = db[collection].insert_one(doc)
    log_event(doc["run_id"], event_kind, event_payload or {}, db=db)
    return res.inserted_id
