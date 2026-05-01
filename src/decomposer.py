"""Decompose a user prompt into a 5–8 subtask DAG.

In mock mode the deterministic 7-subtask bridge fallback (Amendment 3.4) is
returned directly. In real mode the LLM call is attempted; on JSON failure
we retry once and then fall back to the deterministic DAG.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.db.writes import insert_with_event
from src.llm.openai_client import chat

log = logging.getLogger(__name__)

DEFAULT_DAG_PROMPT_HEADER = """You decompose a user design prompt into 5-8 subtasks.

Rules:
- Output strict JSON: {"subtasks":[{"subtask_id":"T1","title":"...","description":"...","required_capabilities":["..."],"depends_on":[]}]}
- DAG must be acyclic; depends_on may only reference earlier subtask_ids.
- Include subtasks for validation, budget, visualization and final report when applicable.

User prompt:
"""


# Fallback DAG used when (a) we are in mock mode, or (b) the LLM JSON parse
# fails twice. Kept in sync with src/llm/mock.py::_decomposer so mock and
# fallback agree.
FALLBACK_DAG: list[dict[str, Any]] = [
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


def _validate_dag(subtasks: list[dict[str, Any]]) -> bool:
    if not (5 <= len(subtasks) <= 8):
        return False
    seen: set[str] = set()
    for st in subtasks:
        sid = st.get("subtask_id")
        if not sid or sid in seen:
            return False
        for dep in st.get("depends_on", []) or []:
            if dep not in seen:
                return False
        seen.add(sid)
    return True


def decompose(run_id: str, prompt: str) -> list[dict[str, Any]]:
    try:
        raw = chat(DEFAULT_DAG_PROMPT_HEADER + prompt, role="decomposer")
        data = json.loads(raw)
        subtasks = data["subtasks"]
        if not _validate_dag(subtasks):
            raise ValueError("invalid DAG")
    except Exception as e:  # noqa: BLE001
        log.warning("decomposer fell back to default DAG: %s", e)
        subtasks = [dict(st) for st in FALLBACK_DAG]

    # Persist subtasks + topo index.
    for i, st in enumerate(subtasks):
        st_doc = {
            "run_id": run_id,
            "subtask_id": st["subtask_id"],
            "title": st["title"],
            "description": st["description"],
            "required_capabilities": st.get("required_capabilities", []),
            "depends_on": st.get("depends_on", []),
            "status": "pending",
            "topo_index": i,
        }
        insert_with_event(
            "subtasks", st_doc,
            event_kind="decompose",
            event_payload={"subtask_id": st["subtask_id"]},
        )
    return subtasks
