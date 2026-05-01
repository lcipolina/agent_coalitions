"""Synthesise final design_specs from subtask_outputs."""
from __future__ import annotations

import json
import logging
from typing import Any

from src.db.client import get_db
from src.db.writes import insert_with_event
from src.llm.openai_client import chat

log = logging.getLogger(__name__)

_FALLBACK_SPEC: dict[str, Any] = {
    "bridge_type": "multi-span_cable_stayed",
    "span_layout": [{"length_m": 200, "supports": ["pier", "pier"]}] * 10,
    "total_length_m": 2000,
    "deck_width_m": 12,
    "lanes": 2,
    "design_live_load_kN_per_m": 12,
    "primary_material": "weathering_steel",
    "deck_material": "concrete",
    "aesthetic_style": "modern_minimal",
}


def synthesise(run_id: str, prompt: str) -> dict:
    db = get_db()
    outputs = list(
        db.subtask_outputs.find({"run_id": run_id}, {"_id": 0}).sort("subtask_id", 1)
    )
    summaries_text = "\n".join(f"- {o['subtask_id']}: {o['summary']}" for o in outputs)
    raw = chat(
        f"User prompt: {prompt}\n\nSubtask summaries:\n{summaries_text}\n\n"
        f"Synthesise a final design_specs JSON.",
        role="synthesizer",
    )
    try:
        spec = json.loads(raw)
    except Exception:  # noqa: BLE001
        log.warning("synthesizer fell back to default spec")
        spec = dict(_FALLBACK_SPEC)
    spec["run_id"] = run_id
    spec.setdefault("validation_status", "pending")
    insert_with_event(
        "design_specs", spec,
        event_kind="design_synthesised",
        event_payload={"bridge_type": spec.get("bridge_type")},
    )
    return spec
