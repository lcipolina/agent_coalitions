"""Validator: evaluate the synthesised spec against the per-run criteria.

The criteria come from the Validator-Spec agent (``src.pipeline.validator_spec``)
which writes them onto the ``runs`` row at the start of the pipeline. Each
criterion has an optional structured ``check`` block that this module knows
how to evaluate generically; criteria with ``check is None`` are reported
as ``qualitative`` and rely on the LLM judge for narrative assessment.

The legacy bridge-domain helpers (``_check_span_to_depth``, …) are kept
intact below because the unit tests import them directly. They are no
longer invoked from ``validate()`` — their behaviour is now expressed by
the bridge-default criteria emitted by the mock validator-spec agent.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.db.client import get_db
from src.db.writes import insert_with_event
from src.llm.openai_client import chat
from src.llm.prompts import render

log = logging.getLogger(__name__)


def _check_span_to_depth(spec: dict) -> dict:
    """Bridge slenderness check: span/depth in [8,18] pass, [4,30] warn, else fail."""
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
    """Verify ``n_supports == n_spans + 1`` and that span lengths sum to total."""
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
    """Bound the gross live-load envelope ``q*w*L`` to plausible bridge magnitudes."""
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
    """Reject materially-impossible primary systems (e.g. timber > 120 m)."""
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
    """Require deck width ≥ 3.5 m per lane (code-minimum lane width)."""
    lanes = spec.get("lanes", 0)
    width = spec.get("deck_width_m", 0)
    needed = lanes * 3.5
    status = "pass" if needed <= width else "fail"
    return {"name": "lane_geometry", "status": status,
            "value": {"lanes": lanes, "deck_width_m": width, "needed_m": needed},
            "note": "ok" if status == "pass" else "deck too narrow"}


def _overall(checks: list[dict]) -> str:
    """Aggregate per-check statuses into the overall run validation status."""
    statuses = {c["status"] for c in checks}
    if "fail" in statuses:
        return "conceptual_fail"
    if "warning" in statuses:
        return "conceptual_pass_with_warnings"
    return "conceptual_pass"


# ---------------------------------------------------------------------------
# Generic criterion dispatcher (used by validate())
# ---------------------------------------------------------------------------
def _resolve_field(spec: dict, path: str) -> Any:
    """Resolve a dotted path into the spec, with a few computed shortcuts.

    Computed fields (not literally in the spec, but derivable):
      - span_to_depth_ratio
      - support_count_consistent  (bool)
      - live_load_total_kN        (q * w * L)
      - deck_width_per_lane_m
    """
    if path == "span_to_depth_ratio":
        layout = spec.get("span_layout") or []
        if not layout or not spec.get("structural_depth_m"):
            return None
        span = max((s.get("length_m", 0) for s in layout), default=0)
        depth = spec.get("structural_depth_m") or max(span / 12.0, 1.0)
        return span / depth if depth > 0 else 0
    if path == "support_count_consistent":
        layout = spec.get("span_layout") or []
        if not layout:
            return None
        n_supports = spec.get("n_supports", len(layout) + 1)
        sum_l = sum(s.get("length_m", 0) for s in layout)
        total = spec.get("total_length_m", sum_l)
        return ((len(layout) + 1) == n_supports
                and abs(sum_l - total) <= 0.02 * max(total, 1))
    if path == "live_load_total_kN":
        if not (spec.get("design_live_load_kN_per_m")
                and spec.get("deck_width_m")
                and spec.get("total_length_m")):
            return None
        return (spec.get("design_live_load_kN_per_m", 0)
                * spec.get("deck_width_m", 0)
                * spec.get("total_length_m", 0))
    if path == "deck_width_per_lane_m":
        lanes = spec.get("lanes", 0) or 0
        width = spec.get("deck_width_m", 0) or 0
        if not lanes or not width:
            return None
        return width / lanes

    cur: Any = spec
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _evaluate_criterion(criterion: dict, spec: dict) -> dict:
    cid = criterion.get("id", "C?")
    name = criterion.get("must_have", cid)
    check = criterion.get("check")
    if not check:
        return {"name": cid, "status": "qualitative", "value": None,
                "note": name}
    op = check.get("op")
    field = check.get("spec_field")
    target = check.get("value")
    actual = _resolve_field(spec, field)
    # If the criterion targets a field this domain's spec doesn't have,
    # demote to "qualitative" rather than failing — a rollercoaster spec
    # has no `span_to_depth_ratio`, but that doesn't mean the design is
    # bad; it means the criterion doesn't apply.
    if op != "present" and actual in (None, "", [], {}):
        return {"name": cid, "status": "qualitative",
                "value": {"actual": None,
                          "expected": {"op": op, "value": target},
                          "field": field},
                "note": f"{name} (field not present in spec)"}
    status = "fail"
    try:
        if op == "lte":
            status = "pass" if actual is not None and actual <= target else "fail"
        elif op == "gte":
            status = "pass" if actual is not None and actual >= target else "fail"
        elif op == "between":
            lo, hi = target
            if actual is None:
                status = "fail"
            elif lo <= actual <= hi:
                status = "pass"
            elif (lo * 0.5) <= actual <= (hi * 1.5):
                status = "warning"
            else:
                status = "fail"
        elif op == "present":
            status = "pass" if actual not in (None, "", [], {}) else "fail"
        elif op == "equals_any":
            status = "pass" if actual in (target or []) else "fail"
    except Exception as exc:  # noqa: BLE001
        log.warning("criterion %s failed to evaluate: %s", cid, exc)
        status = "fail"
    return {"name": cid, "status": status,
            "value": {"actual": actual, "expected": {"op": op, "value": target},
                      "field": field},
            "note": name}


def validate(run_id: str, spec: dict) -> dict:
    """Evaluate the run's criteria against ``spec`` and persist the result.

    Combines structured criterion checks (with overall status aggregated
    over the quantitative ones only) with a per-subtask LLM judge pass
    rating clarity / completeness / consistency.
    """
    db = get_db()
    run_doc = db.runs.find_one({"run_id": run_id}, {"_id": 0, "validation_spec": 1})
    val_spec = (run_doc or {}).get("validation_spec") or {"criteria": []}
    checks = [_evaluate_criterion(c, spec) for c in val_spec.get("criteria", [])]
    # Overall status considers only quantitative outcomes; qualitative
    # criteria are surfaced for the judge / human reviewer.
    quantitative = [c for c in checks if c["status"] != "qualitative"]
    overall = _overall(quantitative) if quantitative else "conceptual_pass_with_warnings"

    # LLM judge per subtask output (clarity / completeness / consistency 0-10).
    judge_scores = []
    outputs = list(db.subtask_outputs.find({"run_id": run_id}, {"_id": 0}))
    for o in outputs:
        raw = chat(
            render("judge", subtask_id=o["subtask_id"], summary=o["summary"]),
            role="judge", subtask_id=o["subtask_id"],
        )
        # Strip markdown code fences (```json ... ```) the LLM sometimes adds.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        try:
            data = json.loads(cleaned)
            # Coerce required fields to expected types.
            data = {
                "subtask_id": str(data.get("subtask_id", o["subtask_id"])),
                "clarity": int(data.get("clarity", 5)),
                "completeness": int(data.get("completeness", 5)),
                "consistency": int(data.get("consistency", 5)),
                "rationale": str(data.get("rationale", ""))[:500],
            }
        except Exception:  # noqa: BLE001
            log.warning("judge JSON parse failed for %s; raw=%r",
                        o["subtask_id"], raw[:200])
            data = {"subtask_id": o["subtask_id"],
                    "clarity": 5, "completeness": 5, "consistency": 5,
                    "rationale": "judge JSON parse failed"}
        judge_scores.append(data)

    doc = {
        "run_id": run_id,
        "checks": checks,
        "overall_status": overall,
        "judge_scores": judge_scores,
        "validation_spec": val_spec,
    }
    insert_with_event(
        "validation_results", doc,
        event_kind="validation_done",
        event_payload={"overall_status": overall, "n_checks": len(checks)},
    )
    return doc
