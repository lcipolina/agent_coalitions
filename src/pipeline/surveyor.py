"""Surveyor agent: prompt-driven quantity take-off + cost roll-up.

The surveyor was originally bridge-hardcoded (deck area × material density,
pier and abutment counts, etc.). This module is now domain-agnostic, mirroring
the Visualiser pattern:

  - **deterministic builder** (``_bridge_qto``) — the legacy bridge heuristic.
    Used as the default when the spec looks like a bridge, and as the fallback
    when the LLM path fails. This keeps the demo stable for the canonical
    bridge prompt regardless of mode.
  - **generic builder** (``_generic_qto``) — a coarse "envelope volume × unit
    rate" heuristic that produces sensible numbers for any spec that exposes a
    length / width / height. Used when the spec clearly is not a bridge and
    the LLM path is unavailable (mock mode).
  - **LLM builder** (``_llm_qto``) — in real mode, the surveyor agent reads the
    spec and the rate card and emits line items directly. The output is parsed
    against a minimal schema and validated; on any failure we fall back to one
    of the deterministic builders so the pipeline never crashes mid-demo.

Either path tags the cost estimate with a ``source`` field so a replay can
tell where the numbers came from.

The narrative paragraph is still produced by ``chat(role="surveyor_narrative")``
and is informational; it does not feed into the totals.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.db.writes import insert_with_event
from src.llm.openai_client import chat
from src.llm.prompts import render

log = logging.getLogger(__name__)

COST_MODEL_PATH = Path(__file__).resolve().parents[2] / "cost_model.json"


def _load_cost_model() -> dict:
    with COST_MODEL_PATH.open() as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Deterministic builders
# ---------------------------------------------------------------------------
def _looks_like_bridge(spec: dict) -> bool:
    """Heuristic: does this spec carry the bridge-shape vocabulary?"""
    bridge_keys = {"span_layout", "deck_width_m", "bridge_type",
                   "primary_material", "total_length_m"}
    return len(bridge_keys & set(spec.keys())) >= 3


def _bridge_qto(spec: dict, cm: dict) -> list[dict]:
    """Crude bridge-domain quantity heuristics — the original surveyor logic."""
    L = spec.get("total_length_m", 0)
    W = spec.get("deck_width_m", 0)
    layout = spec.get("span_layout") or []
    n_supports = max(len(layout) + 1, 2)
    n_piers = max(n_supports - 2, 0)
    n_abutments = 2 if n_supports >= 2 else 0
    primary = (spec.get("primary_material") or "").lower()
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

    if deck_area > 0:
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


def _first_numeric(spec: dict, key_hints: tuple[str, ...]) -> float:
    """Return the first numeric value in ``spec`` whose key contains any hint."""
    for k, v in spec.items():
        if isinstance(v, (int, float)) and any(h in k.lower() for h in key_hints):
            return float(v)
    return 0.0


def _generic_qto(spec: dict, cm: dict) -> list[dict]:
    """Domain-agnostic envelope-volume heuristic.

    Produces a small set of line items sized off whatever length / width /
    height the spec advertises. The numbers are deliberately coarse — the goal
    is "non-zero, defensible estimate for any prompt", not engineering accuracy.
    """
    length = _first_numeric(spec, ("length", "total_length", "span"))
    width = _first_numeric(spec, ("width", "deck_width", "diameter"))
    height = _first_numeric(spec, ("height", "elevation", "depth"))
    if length <= 0:
        length = 100.0  # fallback so non-numeric prompts still cost something
    if width <= 0:
        width = 8.0
    envelope_area = length * max(width, 1.0)

    steel_tonnes = round(envelope_area * 0.10, 1)
    concrete_m3 = round(envelope_area * 0.30, 1)

    items = [
        {"item": "primary structural steel (envelope)", "qty": steel_tonnes,
         "unit": "tonnes", "unit_cost": cm["structural_steel_per_tonne"],
         "subtotal": int(steel_tonnes * cm["structural_steel_per_tonne"])},
        {"item": "structural concrete (envelope)", "qty": concrete_m3,
         "unit": "m3", "unit_cost": cm["structural_concrete_per_m3"],
         "subtotal": int(concrete_m3 * cm["structural_concrete_per_m3"])},
        {"item": "finishing surface", "qty": envelope_area,
         "unit": "m2", "unit_cost": cm["deck_slab_per_m2"],
         "subtotal": int(envelope_area * cm["deck_slab_per_m2"])},
    ]
    if height > 0:
        n_supports = max(int(length // 200) - 1, 0)
        if n_supports:
            items.append({"item": "vertical supports", "qty": n_supports,
                          "unit": "each", "unit_cost": cm["pier_each"],
                          "subtotal": n_supports * cm["pier_each"]})
    return items


def _deterministic_qto(spec: dict, cm: dict) -> tuple[list[dict], str]:
    if _looks_like_bridge(spec):
        return _bridge_qto(spec, cm), "deterministic_bridge"
    return _generic_qto(spec, cm), "deterministic_generic"


# ---------------------------------------------------------------------------
# LLM builder
# ---------------------------------------------------------------------------
def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _llm_two_bucket(spec: dict, cm: dict) -> dict | None:
    """Ask the LLM for a 2-bucket {materials_eur, labour_hours, rate} estimate.

    Returns ``None`` on any parse / validation failure so the caller can
    fall back to the deterministic path.
    """
    spec_for_prompt = {k: v for k, v in spec.items() if k != "_id"}
    raw = chat(
        render("surveyor_qto", spec=spec_for_prompt, cost_model=cm),
        role="surveyor_qto",
    )
    try:
        data = json.loads(_strip_code_fences(raw))
        materials = float(data["materials_eur"])
        hours = float(data["labour_hours"])
        rate = float(data["labour_rate_eur_per_h"])
        if materials < 0 or hours < 0 or rate < 0:
            raise ValueError("negative value")
        return {
            "materials_eur": int(materials),
            "labour_hours": int(hours),
            "labour_rate_eur_per_h": int(rate),
            "rationale": str(data.get("rationale", ""))[:500],
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("surveyor_qto LLM path failed (%s); falling back", exc)
        return None


def _deterministic_two_bucket(spec: dict, cm: dict) -> tuple[dict, str]:
    """Roll the legacy detailed builders up into the 2-bucket shape.

    Materials = sum of all detailed line-item subtotals.
    Labour hours = materials_eur × labour_share_pct / labour_rate, with
    industry-rule-of-thumb defaults (≈35% of materials at a €90/h blended
    rate for conceptual civil/structural work).
    """
    if _looks_like_bridge(spec):
        items = _bridge_qto(spec, cm)
        flavour = "deterministic_bridge"
    else:
        items = _generic_qto(spec, cm)
        flavour = "deterministic_generic"
    materials = int(sum(i["subtotal"] for i in items))
    rate = 90  # blended €/h
    labour_share = 0.35
    hours = int(materials * labour_share / rate) if materials > 0 else 0
    return ({
        "materials_eur": materials,
        "labour_hours": hours,
        "labour_rate_eur_per_h": rate,
        "rationale": "Detailed quantity take-off rolled up into materials + labour buckets.",
        "_detail": items,  # kept for diagnostics, not surfaced in the table
    }, flavour)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def estimate(run_id: str, spec: dict) -> dict:
    """Build a 2-bucket conceptual cost estimate for ``run_id``.

    Output line items are exactly two: **Materials** (rolled-up rate-card
    cost of physical components) and **Man-hours** (total construction
    labour hours × a blended rate). This is intentionally simple — at the
    conceptual stage anything more granular is false precision.

    Mock mode uses the deterministic builders so the demo is reproducible.
    Real mode tries the LLM path first and falls back to the deterministic
    builder on any parse / validation failure.
    """
    cm = _load_cost_model()

    if settings.use_mock_llm:
        bucket, source = _deterministic_two_bucket(spec, cm)
    else:
        llm_bucket = _llm_two_bucket(spec, cm)
        if llm_bucket:
            bucket, source = llm_bucket, "llm"
        else:
            bucket, source = _deterministic_two_bucket(spec, cm)
            source = f"{source}_fallback"

    materials_eur = int(bucket["materials_eur"])
    hours = int(bucket["labour_hours"])
    rate = int(bucket["labour_rate_eur_per_h"])
    labour_eur = hours * rate

    items = [
        {"category": "Materials", "qty": 1, "unit": "lump_sum",
         "unit_cost": materials_eur, "subtotal": materials_eur},
        {"category": "Man-hours", "qty": hours, "unit": "hours",
         "unit_cost": rate, "subtotal": labour_eur},
    ]

    subtotal = materials_eur + labour_eur
    contingency = subtotal * cm["contingency_pct"] / 100
    total = int(subtotal + contingency)

    narrative = chat(
        render(
            "surveyor_narrative",
            subtotal=int(subtotal),
            currency=cm["currency"],
            finishing_pct=0,
            contingency_pct=cm["contingency_pct"],
            total=total,
            primary_material=spec.get("primary_material", ""),
            line_items=items,
        ),
        role="surveyor_narrative",
    )

    doc = {
        "run_id": run_id,
        "currency": cm["currency"],
        "line_items": items,
        "subtotal": int(subtotal),
        "finishing_premium_pct": 0,
        "contingency_pct": cm["contingency_pct"],
        "total": total,
        "narrative": narrative,
        "rationale": bucket.get("rationale", ""),
        "source": source,
    }
    insert_with_event(
        "cost_estimates", doc,
        event_kind="cost_estimated",
        event_payload={"total": total, "currency": cm["currency"],
                       "source": source},
    )
    return doc
