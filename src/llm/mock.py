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
    return (
        f"[mock-marshal {subtask_id}] Coalition, please post your contribution "
        f"focusing on the subtask requirements. Cite upstream summaries where relevant."
    )


def _marshal_reconcile(prompt: str, subtask_id: str = "T?", **_: Any) -> str:
    return (
        f"[mock-marshal {subtask_id}] Reconciled summary: combining contributions, "
        f"the consensus is recorded as the subtask output."
    )


def _agent(prompt: str, agent_id: str = "agent_xxx", subtask_id: str = "T?", **_: Any) -> str:
    return (
        f"[mock-{agent_id} {subtask_id}] Contribution: applies my skills to the subtask; "
        f"recommend conservative defaults and flag a single open question for the marshal."
    )


def _synthesizer(prompt: str, **_: Any) -> str:
    return json.dumps({
        "bridge_type": "multi-span_cable_stayed",
        "span_layout": [{"length_m": 200, "supports": ["pier", "pier"]}] * 10,
        "total_length_m": 2000,
        "deck_width_m": 12,
        "lanes": 2,
        "design_live_load_kN_per_m": 12,
        "primary_material": "weathering_steel",
        "deck_material": "concrete",
        "aesthetic_style": "modern_minimal",
        "validation_status": "pending"
    })


def _surveyor_narrative(prompt: str, **_: Any) -> str:
    return (
        "Cost narrative (mock): primary structural steel dominates, deck slab and pier "
        "construction are secondary drivers; 15% contingency applied per spec."
    )


def _reporter(prompt: str, **_: Any) -> str:
    return (
        "# Conceptual Bridge Design Brief (mock)\n\n"
        "Conceptual design produced by an experimental multi-agent system. "
        "Not certified engineering. Not for construction.\n\n"
        "## Summary\nMulti-span cable-stayed, weathering steel primary with concrete deck. "
        "Validation passed with warnings; cost estimate populated.\n"
    )


def _judge(prompt: str, subtask_id: str = "T?", **_: Any) -> str:
    return json.dumps({
        "subtask_id": subtask_id,
        "clarity": 7,
        "completeness": 7,
        "consistency": 8,
        "rationale": "Mock judge: contribution is clear, covers the requirements, internally consistent."
    })


_ROUTERS = {
    "decomposer": _decomposer,
    "marshal_kickoff": _marshal_kickoff,
    "marshal_reconcile": _marshal_reconcile,
    "agent": _agent,
    "synthesizer": _synthesizer,
    "surveyor_narrative": _surveyor_narrative,
    "reporter": _reporter,
    "judge": _judge,
}


def _short(s: str, n: int = 24) -> str:
    s = s.replace("\n", " ").strip()
    return s[:n] + ("..." if len(s) > n else "")
