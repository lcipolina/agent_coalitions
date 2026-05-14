"""Validator-Spec agent: derive prompt-level acceptance criteria.

This stage runs after decompose and before execute. It reads the user
prompt and produces a small, structured list of must-have criteria that
the final design will be checked against.

Two responsibilities:
  1. Persist the validation_spec on the runs row so it is part of the
     replay surface (no LLM calls on replay).
  2. Hand the criteria to the marshals during round-0 kickoff so each
     coalition is briefed on what the design will be judged on.

Schema produced::

    {
      "criteria": [
        {
          "id": "C1",
          "must_have": "<plain English requirement>",
          "rationale": "<short reason>",
          "check": null | {
            "spec_field": "<dotted path>",
            "op": "lte" | "gte" | "between" | "present" | "equals_any",
            "value": <number | [lo, hi] | [..]>
          }
        }
      ],
      "narrative": "<one paragraph>"
    }

In mock mode the criteria are bridge-domain defaults. In real mode the
LLM derives them from the prompt; on parse / validation failure we fall
back to a single qualitative criterion so the pipeline never crashes.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.db.client import get_db
from src.db.writes import log_event
from src.llm.openai_client import chat
from src.llm.prompts import render

log = logging.getLogger(__name__)

_ALLOWED_OPS = {"lte", "gte", "between", "present", "equals_any"}


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _validate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("top-level must be an object")
    crit = data.get("criteria")
    if not isinstance(crit, list) or not crit:
        raise ValueError("'criteria' must be a non-empty array")
    clean: list[dict[str, Any]] = []
    for i, c in enumerate(crit):
        if not isinstance(c, dict):
            raise ValueError(f"criterion #{i} not an object")
        cid = str(c.get("id") or f"C{i + 1}")
        must = c.get("must_have")
        if not isinstance(must, str) or not must.strip():
            raise ValueError(f"criterion #{i} missing must_have")
        check = c.get("check")
        if check is not None:
            if not isinstance(check, dict):
                raise ValueError(f"criterion {cid} 'check' must be object or null")
            if check.get("op") not in _ALLOWED_OPS:
                raise ValueError(f"criterion {cid} op not in {_ALLOWED_OPS}")
            if not isinstance(check.get("spec_field"), str):
                raise ValueError(f"criterion {cid} missing spec_field")
        clean.append({
            "id": cid,
            "must_have": must.strip(),
            "rationale": str(c.get("rationale", "")),
            "check": check,
        })
    return {
        "criteria": clean,
        "narrative": str(data.get("narrative", "")),
    }


_FALLBACK_SPEC = {
    "criteria": [
        {"id": "C1",
         "must_have": "The design must be internally consistent and address every "
                      "explicit requirement of the user prompt.",
         "rationale": "Generic fallback when the validator-spec agent cannot be parsed.",
         "check": None},
    ],
    "narrative": "Generic fallback validation specification.",
}


def derive_validation_spec(run_id: str, prompt: str) -> dict[str, Any]:
    """Derive the acceptance-criteria spec from the prompt and persist it.

    Args:
        run_id: The current run identifier.
        prompt: The user prompt from which to derive criteria.

    Returns:
        dict[str, Any]: The validated ``validation_spec`` stored on the run.
    """
    raw = chat(render("validator_spec", prompt=prompt), role="validator_spec")
    try:
        spec = _validate(json.loads(_strip_code_fences(raw)))
    except Exception as exc:  # noqa: BLE001 - any LLM failure is recoverable
        log.warning("validator_spec parse failed (%s); using fallback", exc)
        spec = dict(_FALLBACK_SPEC)

    db = get_db()
    db.runs.update_one(
        {"run_id": run_id},
        {"$set": {"validation_spec": spec}},
    )
    log_event(run_id, "validation_spec_derived",
              {"n_criteria": len(spec["criteria"])})
    return spec
