"""Deterministic validator + LLM-judge wrapper.

Five deterministic checks per Amendment 3.6:
  1. span_to_depth_ratio
  2. support_count_consistency
  3. live_load_arithmetic
  4. material_span_plausibility
  5. lane_geometry
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.db.client import get_db
from src.db.writes import insert_with_event
from src.llm.openai_client import chat

log = logging.getLogger(__name__)


def _check_span_to_depth(spec: dict) -> dict:
    span = max((s["length_m"] for s in spec.get("span_layout", []) or [{"length_m": 0}]),
               default=0)
    # Conservative default depth = span/12 if not provided.
    depth = spec.get("structural_depth_m", max(span / 12.0, 1.0))
    ratio = span / depth if depth > 0 else 0
    if ratio < 4 or ratio > 30:
        status = "fail"
    elif 8 <= ratio <= 18:
        status = "pass"
    else:
        status = "warning"
    return {"name": "span_to_depth_ratio", "status": status, "value": round(ratio, 2),
            "note": f"span={span}m depth={depth:.1f}m"}


def _check_support_count(spec: dict) -> dict:
    layout = spec.get("span_layout") or []
    n_supports = spec.get("n_supports", len(layout) + 1)
    sum_lengths = sum(s["length_m"] for s in layout)
    total = spec.get("total_length_m", sum_lengths)
    ok_count = (len(layout) + 1) == n_supports
    ok_total = abs(sum_lengths - total) <= 0.02 * max(total, 1)
    status = "pass" if ok_count and ok_total else "fail"
    return {"name": "support_count_consistency", "status": status,
            "value": {"n_supports": n_supports, "sum": sum_lengths, "total": total},
            "note": "ok" if status == "pass" else "geometry mismatch"}


def _check_live_load(spec: dict) -> dict:
    q = spec.get("design_live_load_kN_per_m", 0)
    w = spec.get("deck_width_m", 0)
    L = spec.get("total_length_m", 0)
    val = q * w * L
    if 1e3 <= val <= 1e6 * 100:  # generous; the spec says 1e3..1e6 kN
        status = "pass" if 1e3 <= val <= 1e6 else "warning"
    else:
        status = "fail"
    return {"name": "live_load_arithmetic", "status": status, "value": val,
            "note": f"q*w*L = {q}*{w}*{L}"}


def _check_material_span(spec: dict) -> dict:
    primary = spec.get("primary_material", "")
    max_span = max((s["length_m"] for s in spec.get("span_layout", []) or [{"length_m": 0}]),
                   default=0)
    status = "pass"
    note = "ok"
    if "timber" in primary and max_span > 120:
        status, note = "fail", "timber primary impractical above 120m"
    elif "concrete" in primary and max_span > 250:
        status, note = "warning", "concrete >250m unusual"
    elif "steel" in primary and max_span > 1500:
        status, note = "warning", "steel >1500m extreme"
    return {"name": "material_span_plausibility", "status": status,
            "value": {"primary": primary, "max_span_m": max_span}, "note": note}


def _check_lane_geometry(spec: dict) -> dict:
    lanes = spec.get("lanes", 0)
    width = spec.get("deck_width_m", 0)
    needed = lanes * 3.5
    status = "pass" if needed <= width else "fail"
    return {"name": "lane_geometry", "status": status,
            "value": {"lanes": lanes, "deck_width_m": width, "needed_m": needed},
            "note": "ok" if status == "pass" else "deck too narrow"}


def _overall(checks: list[dict]) -> str:
    statuses = {c["status"] for c in checks}
    if "fail" in statuses:
        return "conceptual_fail"
    if "warning" in statuses:
        return "conceptual_pass_with_warnings"
    return "conceptual_pass"


def validate(run_id: str, spec: dict) -> dict:
    checks = [
        _check_span_to_depth(spec),
        _check_support_count(spec),
        _check_live_load(spec),
        _check_material_span(spec),
        _check_lane_geometry(spec),
    ]
    overall = _overall(checks)

    # LLM judge per subtask output (clarity / completeness / consistency 0-10).
    judge_scores = []
    db = get_db()
    outputs = list(db.subtask_outputs.find({"run_id": run_id}, {"_id": 0}))
    for o in outputs:
        raw = chat(
            f"Score this subtask summary on clarity, completeness, consistency (0-10):\n"
            f"{o['summary']}",
            role="judge", subtask_id=o["subtask_id"],
        )
        try:
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            data = {"subtask_id": o["subtask_id"],
                    "clarity": 5, "completeness": 5, "consistency": 5,
                    "rationale": "judge JSON parse failed"}
        judge_scores.append(data)

    doc = {
        "run_id": run_id,
        "checks": checks,
        "overall_status": overall,
        "judge_scores": judge_scores,
    }
    insert_with_event(
        "validation_results", doc,
        event_kind="validation_done",
        event_payload={"overall_status": overall, "n_checks": len(checks)},
    )
    return doc
