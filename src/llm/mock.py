"""Deterministic mock LLM for offline development.

Provides ``embed`` (hashed pseudo-embedding) and ``chat`` (templated stubs) so
the entire pipeline can run with USE_MOCK_LLM=true.

The embedding is a 1536-dim L2-normalised vector derived from a SHA-256 hash
of the input text, fanned out via a Mersenne-Twister seeded with the digest.
This gives stable, content-dependent vectors that satisfy cosine-similarity
math (similar strings will not be especially similar — the mock is for
plumbing, not retrieval quality).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

EMBEDDING_DIM = 1536


def _seed_from_text(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Return a deterministic, content-keyed L2-normalised pseudo-embedding."""
    rng = np.random.default_rng(_seed_from_text(text))
    v = rng.standard_normal(dim).astype(np.float32)
    n = float(np.linalg.norm(v))
    if n > 0:
        v = v / n
    return v.tolist()


def chat(prompt: str, role: str = "agent", **kwargs: Any) -> str:
    """Return a deterministic stub response keyed by role.

    Roles: decomposer, marshal_kickoff, marshal_reconcile, agent,
    synthesizer, surveyor_narrative, reporter, judge.
    """
    handler = _ROUTERS.get(role, _default_chat)
    return handler(prompt, **kwargs)


def _default_chat(prompt: str, **_: Any) -> str:
    return f"[mock:{_short(prompt)}] generic response"


def _decomposer(prompt: str, **_: Any) -> str:
    # Deterministic 7-subtask bridge DAG (per MVP_DESIGN §3.4 fallback).
    subtasks = [
        {"subtask_id": "T1", "title": "Site & geometry",
         "description": "Banks, alignment, span layout, approach grades.",
         "required_capabilities": ["site planning", "geometry", "alignment"],
         "depends_on": []},
        {"subtask_id": "T2", "title": "Load profile",
         "description": "Live, dead, dynamic, wind and seismic loading.",
         "required_capabilities": ["traffic load modelling", "structural load estimation"],
         "depends_on": []},
        {"subtask_id": "T3", "title": "Material selection",
         "description": "Primary structural material balancing cost, durability, aesthetic.",
         "required_capabilities": ["materials science", "cost analysis", "constructability"],
         "depends_on": ["T1", "T2"]},
        {"subtask_id": "T4", "title": "Structural system",
         "description": "Truss / cable-stayed / arch system; member sizing.",
         "required_capabilities": ["structural steel design", "cable-stayed bridges", "truss bridges"],
         "depends_on": ["T1", "T2", "T3"]},
        {"subtask_id": "T5", "title": "Aesthetic & elevation guidance",
         "description": "Form, proportions, lighting, elevation rendering inputs.",
         "required_capabilities": ["architectural aesthetics", "elevation rendering"],
         "depends_on": ["T1", "T4"]},
        {"subtask_id": "T6", "title": "Validation prep",
         "description": "Inputs to deterministic checks: span/depth, lane geometry, load arithmetic.",
         "required_capabilities": ["numerical validation", "applied mathematics"],
         "depends_on": ["T3", "T4"]},
        {"subtask_id": "T7", "title": "Final synthesis brief",
         "description": "Consolidated design specification and report.",
         "required_capabilities": ["technical writing", "executive summary drafting"],
         "depends_on": ["T1", "T2", "T3", "T4", "T5", "T6"]},
    ]
    return json.dumps({"subtasks": subtasks})


def _marshal_kickoff(prompt: str, subtask_id: str = "T?", **_: Any) -> str:
    # Surface the validation criteria block from the rendered prompt (if any)
    # so the Blackboard tab shows the marshal briefing the team on what the
    # work will be judged on.
    criteria_block = ""
    if "acceptance criteria" in prompt.lower():
        # Pull out the bullet list of criterion ids -> must_haves.
        lines = []
        capture = False
        for line in prompt.splitlines():
            if "acceptance criteria" in line.lower():
                capture = True
                continue
            if capture:
                if line.startswith("- ["):
                    lines.append(line.strip())
                elif lines and not line.strip():
                    break
        if lines:
            criteria_block = (
                "\nKeep these acceptance criteria in mind:\n"
                + "\n".join(lines[:5])
            )
    return (
        f"[marshal {subtask_id}] Team, please post your contribution "
        f"focusing on the subtask requirements. Cite upstream summaries where relevant."
        f"{criteria_block}"
    )


_MARSHAL_RECONCILE_BY_PREFIX: dict[str, str] = {
    "T1": ("Site & geometry consensus: 2 km alignment with 10 spans of ~200 m. "
           "Approach grades held under 4%. Pier locations clear of the navigation "
           "channel; abutments on competent ground both banks."),
    "T2": ("Load profile consensus: HA + 33 t HB live load, 2.5 kN/m² superimposed "
           "dead, dynamic factor 1.25. Wind reference 38 m/s; seismic peak ground "
           "acceleration 0.10 g. Fatigue category C for primary girders."),
    "T3": ("Material selection consensus: weathering steel primary girders for "
           "durability and minimal maintenance; reinforced-concrete deck slab "
           "with a polymer wearing course. Lifecycle cost beats painted steel "
           "by ~12% over 60 years."),
    "T4": ("Structural system consensus: multi-span cable-stayed with composite "
           "deck on weathering-steel edge girders; pylon spacing every other "
           "internal pier. Stay-cable layout fanned, deck depth ~1.5 m."),
    "T5": ("Aesthetic & elevation consensus: slender deck, tapered concrete "
           "pylons, asymmetric stay arrangement at navigation pier. Night "
           "lighting along the pylons; warm-grey palette to age with the "
           "weathering-steel patina."),
    "T6": ("Validation prep consensus: span/depth ratios within passable band, "
           "support count consistent with span layout, lane geometry leaves a "
           "1.0 m shoulder per side. Dynamic deflection check flagged for "
           "next stage."),
    "T7": ("Synthesis brief consensus: brief is internally consistent. "
           "Recommended next milestones are a wind tunnel review of the deck "
           "section and a value-engineering review of pylon proportions."),
}


def _marshal_reconcile(prompt: str, subtask_id: str = "T?", **_: Any) -> str:
    return _MARSHAL_RECONCILE_BY_PREFIX.get(
        subtask_id,
        f"[marshal {subtask_id}] Reconciled summary: contributions merged; "
        f"consensus recorded as the subtask output.",
    )


def _agent(prompt: str, agent_id: str = "agent_xxx", subtask_id: str = "T?", **_: Any) -> str:
    return (
        f"[{agent_id} {subtask_id}] Contribution: applies my skills to the subtask; "
        f"recommend conservative defaults and flag a single open question for the marshal."
    )


def _synthesizer(prompt: str, **_: Any) -> str:
    return json.dumps({
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
        # Bridge-shaped fields kept for the deterministic geometry path.
        "bridge_type": "multi-span_cable_stayed",
        "span_layout": [{"length_m": 200, "supports": ["pier", "pier"]}] * 10,
        "total_length_m": 2000,
        "deck_width_m": 12,
        "lanes": 2,
        "design_live_load_kN_per_m": 12,
        "deck_material": "concrete",
        "validation_status": "pending"
    })


def _surveyor_narrative(prompt: str, **_: Any) -> str:
    # Stay deliberately generic: the line items vary per run / per domain,
    # so we hand the user a sentence that's true for any roll-up.
    return (
        "Cost roll-up dominated by primary structural materials and major "
        "surface finishings; conceptual-stage estimate, expect 20-30% drift "
        "as the design firms up."
    )


def _surveyor_qto(prompt: str, **_: Any) -> str:
    # Two-bucket mock estimate (materials + labour).
    return json.dumps({
        "materials_eur": 1_000_000,
        "labour_hours": 4_000,
        "labour_rate_eur_per_h": 90,
        "rationale": "Mock conceptual estimate; deterministic QTO is preferred.",
    })


def _reporter(prompt: str, **_: Any) -> str:
    return (
        "# Conceptual Design Brief\n\n"
        "Conceptual design produced by an experimental multi-agent system. "
        "Not certified engineering. Not for construction.\n\n"
        "## Summary\nMulti-span cable-stayed, weathering steel primary with concrete deck. "
        "Validation passed with warnings; cost estimate populated.\n"
    )


def _judge(prompt: str, subtask_id: str = "T?", **_: Any) -> str:
    # Vary per-subtask deterministically so the judge tab looks alive.
    seed = int(hashlib.sha256(subtask_id.encode()).hexdigest(), 16)
    rng = np.random.default_rng(seed)
    clarity = int(6 + rng.integers(0, 4))         # 6..9
    completeness = int(6 + rng.integers(0, 4))    # 6..9
    consistency = int(6 + rng.integers(0, 4))     # 6..9
    rationales = [
        "Numbers tie back cleanly to upstream load assumptions.",
        "Reads well; one structural figure could use a sanity-check note.",
        "Strong on aesthetic guidance, lighter on quantitative justification.",
        "Geometry and span layout consistent with the alignment brief.",
        "Material rationale is reasonable; watch concrete creep at long spans.",
        "Validation inputs cleanly enumerated; nothing left implicit.",
        "Synthesis brief consolidates upstream summaries without contradiction.",
        "Lane geometry and deck width tie cleanly to the traffic brief.",
        "Cost framing is solid; recommend a sensitivity sweep on steel price.",
        "Edge cases covered (wind, seismic) at conceptual depth; deflection still open.",
        "Pier spacing logic follows from span layout; foundation type left to next stage.",
        "Aesthetic narrative aligns with material choice; lighting plan is a follow-up.",
        "Live-load arithmetic correct; conservative on dynamic factor.",
        "Set-cover rationale traceable to the skill embeddings retrieved.",
    ]
    # Spread rationale across more buckets by mixing in score signal.
    idx = (seed + clarity * 31 + completeness * 17 + consistency * 7) % len(rationales)
    return json.dumps({
        "subtask_id": subtask_id,
        "clarity": clarity,
        "completeness": completeness,
        "consistency": consistency,
        "rationale": rationales[idx],
    })


def _validator_spec(prompt: str, **_: Any) -> str:
    """Bridge-default criteria roughly mirroring the legacy 5 deterministic checks."""
    return json.dumps({
        "criteria": [
            {"id": "C1",
             "must_have": "Span-to-depth ratio of the longest span lies in [8, 18].",
             "rationale": "Standard structural slenderness band.",
             "check": {"spec_field": "span_to_depth_ratio", "op": "between", "value": [8, 18]}},
            {"id": "C2",
             "must_have": "Support count is consistent with the span layout.",
             "rationale": "Every span ends on a support.",
             "check": {"spec_field": "support_count_consistent", "op": "equals_any", "value": [True]}},
            {"id": "C3",
             "must_have": "Total live-load capacity (q*w*L) lies in [1e3, 1e6] kN.",
             "rationale": "Bounds the design between sidewalk-only and abnormal heavy-haulage.",
             "check": {"spec_field": "live_load_total_kN", "op": "between", "value": [1000, 1000000]}},
            {"id": "C4",
             "must_have": "Primary structural material matches the longest span (no timber > 120 m, no concrete > 250 m).",
             "rationale": "Guards against materially-impossible primary system.",
             "check": None},
            {"id": "C5",
             "must_have": "Deck width accommodates the lane count at >= 3.5 m per lane.",
             "rationale": "Code-minimum lane width.",
             "check": {"spec_field": "deck_width_per_lane_m", "op": "gte", "value": 3.5}},
        ],
        "narrative": ("Bridge-domain default criteria. The marshals should "
                      "treat span/depth, support consistency, live-load bounds, "
                      "material/span coherence and lane geometry as the conceptual "
                      "validation gate."),
    })


_ROUTERS = {
    "decomposer": _decomposer,
    "marshal_kickoff": _marshal_kickoff,
    "marshal_reconcile": _marshal_reconcile,
    "agent": _agent,
    "synthesizer": _synthesizer,
    "surveyor_narrative": _surveyor_narrative,
    "surveyor_qto": _surveyor_qto,
    "reporter": _reporter,
    "judge": _judge,
    "validator_spec": _validator_spec,
}


def _short(s: str, n: int = 24) -> str:
    s = s.replace("\n", " ").strip()
    return s[:n] + ("..." if len(s) > n else "")
