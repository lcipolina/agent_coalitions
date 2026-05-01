"""Quantity-take-off heuristics + cost roll-up + LLM narrative."""
from __future__ import annotations

import json
from pathlib import Path

from src.db.writes import insert_with_event
from src.llm.openai_client import chat
from src.llm.prompts import render

COST_MODEL_PATH = Path(__file__).resolve().parents[2] / "cost_model.json"


def _load_cost_model() -> dict:
    with COST_MODEL_PATH.open() as f:
        return json.load(f)


def _qto(spec: dict) -> list[dict]:
    """Crude quantity heuristics — good enough for a conceptual estimate."""
    cm = _load_cost_model()
    L = spec.get("total_length_m", 0)
    W = spec.get("deck_width_m", 0)
    layout = spec.get("span_layout") or []
    n_supports = max(len(layout) + 1, 2)
    n_piers = max(n_supports - 2, 0)
    n_abutments = 2 if n_supports >= 2 else 0
    primary = spec.get("primary_material", "")
    deck_area = L * W

    items: list[dict] = []
    if "weathering" in primary:
        tonnes = round(deck_area * 0.18, 1)
        items.append({"item": "weathering steel", "qty": tonnes, "unit": "tonnes",
                      "unit_cost": cm["weathering_steel_per_tonne"],
                      "subtotal": int(tonnes * cm["weathering_steel_per_tonne"])})
    elif "steel" in primary:
        tonnes = round(deck_area * 0.16, 1)
        items.append({"item": "structural steel", "qty": tonnes, "unit": "tonnes",
                      "unit_cost": cm["structural_steel_per_tonne"],
                      "subtotal": int(tonnes * cm["structural_steel_per_tonne"])})
    elif "concrete" in primary:
        m3 = round(deck_area * 0.6, 1)
        items.append({"item": "structural concrete", "qty": m3, "unit": "m3",
                      "unit_cost": cm["structural_concrete_per_m3"],
                      "subtotal": int(m3 * cm["structural_concrete_per_m3"])})

    items.append({"item": "deck slab", "qty": deck_area, "unit": "m2",
                  "unit_cost": cm["deck_slab_per_m2"],
                  "subtotal": int(deck_area * cm["deck_slab_per_m2"])})
    if n_piers:
        items.append({"item": "piers", "qty": n_piers, "unit": "each",
                      "unit_cost": cm["pier_each"],
                      "subtotal": n_piers * cm["pier_each"]})
    if n_abutments:
        items.append({"item": "abutments", "qty": n_abutments, "unit": "each",
                      "unit_cost": cm["abutment_each"],
                      "subtotal": n_abutments * cm["abutment_each"]})
    return items


def estimate(run_id: str, spec: dict) -> dict:
    cm = _load_cost_model()
    items = _qto(spec)
    subtotal = sum(i["subtotal"] for i in items)
    finishing = subtotal * cm["finishing_premium_pct"] / 100
    contingency = (subtotal + finishing) * cm["contingency_pct"] / 100
    total = int(subtotal + finishing + contingency)

    narrative = chat(
        render(
            "surveyor_narrative",
            subtotal=int(subtotal),
            currency=cm["currency"],
            finishing_pct=cm["finishing_premium_pct"],
            contingency_pct=cm["contingency_pct"],
            total=total,
            primary_material=spec.get("primary_material", ""),
        ),
        role="surveyor_narrative",
    )

    doc = {
        "run_id": run_id,
        "currency": cm["currency"],
        "line_items": items,
        "subtotal": int(subtotal),
        "finishing_premium_pct": cm["finishing_premium_pct"],
        "contingency_pct": cm["contingency_pct"],
        "total": total,
        "narrative": narrative,
    }
    insert_with_event(
        "cost_estimates", doc,
        event_kind="cost_estimated",
        event_payload={"total": total, "currency": cm["currency"]},
    )
    return doc
