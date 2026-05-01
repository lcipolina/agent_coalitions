"""Synthesise final design_specs from subtask_outputs."""
from __future__ import annotations

import json
import logging
from typing import Any

from src.db.client import get_db
from src.db.writes import insert_with_event
from src.llm.openai_client import chat
from src.llm.prompts import render

log = logging.getLogger(__name__)

_FALLBACK_SPEC: dict[str, Any] = {
    "design_type": "multi_span_cable_stayed_bridge",
    "domain": "bridge",
    "primary_material": "weathering_steel",
    "secondary_material": "high_strength_concrete",
    "aesthetic_style": "modern_minimal",
    "dimensions": {"length_m": 2000, "width_m": 12, "height_m": 60},
    "characteristics": {
        "total_length_m": 2000,
        "longest_span_m": 200,
        "deck_width_m": 12,
        "lanes": 2,
        "design_live_load_kN_per_m": 12,
    },
    # Bridge-shaped fields kept for the deterministic geometry fallback.
    "bridge_type": "multi-span_cable_stayed",
    "span_layout": [{"length_m": 200, "supports": ["pier", "pier"]}] * 10,
    "total_length_m": 2000,
    "deck_width_m": 12,
    "lanes": 2,
    "design_live_load_kN_per_m": 12,
    "deck_material": "concrete",
}


def synthesise(run_id: str, prompt: str) -> dict:
    """Combine subtask outputs into a single design spec and persist it.

    Falls back to :data:`_FALLBACK_SPEC` if the LLM response cannot be
    parsed as JSON, so the pipeline always produces something downstream
    stages can consume.
    """
    db = get_db()
    outputs = list(
        db.subtask_outputs.find({"run_id": run_id}, {"_id": 0}).sort("subtask_id", 1)
    )
    raw = chat(
        render("synthesizer", prompt=prompt, outputs=outputs),
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
        event_payload={
            "design_type": spec.get("design_type") or spec.get("bridge_type"),
            "domain": spec.get("domain"),
        },
    )
    return spec
