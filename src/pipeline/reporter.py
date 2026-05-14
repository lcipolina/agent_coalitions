"""Final markdown report builder."""
from __future__ import annotations

from src.db.client import get_db
from src.db.writes import insert_with_event
from src.llm.openai_client import chat
from src.llm.prompts import render

DISCLAIMER = (
    "*Conceptual design produced by an experimental multi-agent system. "
    "Not certified engineering. Not for construction.*"
)


def _format_value(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        # Compact number with thousands separator.
        return f"{v:,}" if isinstance(v, int) or v == int(v) else f"{v:,.2f}"
    if isinstance(v, list):
        return ", ".join(_format_value(x) for x in v) if v else "—"
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_format_value(val)}" for k, val in v.items()) or "—"
    return str(v) if v not in (None, "") else "—"


_HUMAN_LABELS = {
    "design_type": "Design type",
    "domain": "Domain",
    "primary_material": "Primary material",
    "secondary_material": "Secondary material",
    "deck_material": "Deck material",
    "aesthetic_style": "Aesthetic style",
    "total_length_m": "Total length (m)",
    "deck_width_m": "Deck width (m)",
    "lanes": "Lanes",
    "design_live_load_kN_per_m": "Design live load (kN/m)",
    "structural_depth_m": "Structural depth (m)",
}


def _humanise(key: str) -> str:
    if key in _HUMAN_LABELS:
        return _HUMAN_LABELS[key]
    # snake_case → Title Case, keeping unit suffixes legible.
    parts = key.replace("_", " ").split()
    return " ".join(p if p.isupper() else p.capitalize() for p in parts)


def _design_characteristics_md(spec: dict) -> str:
    """Render the final design characteristics as a compact markdown table.

    Domain-agnostic: walks the canonical top-level fields plus the
    free-form ``characteristics`` and ``dimensions`` sub-dicts. Skips
    pipeline-internal keys (run_id, validation_status, _id, etc.).
    """
    skip = {"run_id", "validation_status", "_id", "characteristics",
            "dimensions", "span_layout"}
    # Hide the legacy bridge-shaped fields entirely when this isn't a bridge.
    if (spec.get("domain") or "").lower() != "bridge":
        skip |= {"bridge_type", "total_length_m", "deck_width_m", "lanes",
                 "design_live_load_kN_per_m", "structural_depth_m",
                 "deck_material"}

    rows: list[tuple[str, str]] = []
    for k, v in spec.items():
        if k in skip:
            continue
        if v in (None, "", 0, [], {}):
            continue
        rows.append((_humanise(k), _format_value(v)))

    dims = spec.get("dimensions") or {}
    for k, v in dims.items():
        if v in (None, "", 0):
            continue
        rows.append((_humanise(k), _format_value(v)))

    chars = spec.get("characteristics") or {}
    for k, v in chars.items():
        if v in (None, ""):
            continue
        rows.append((_humanise(k), _format_value(v)))

    # Bridges: derive span info if span_layout is present.
    layout = spec.get("span_layout") or []
    if layout:
        spans = [s.get("length_m", 0) for s in layout]
        rows.append(("Number of spans", str(len(layout))))
        rows.append(("Longest span (m)", _format_value(max(spans))))

    if not rows:
        rows = [("Design", spec.get("design_type") or spec.get("bridge_type")
                 or "(unspecified)")]

    md = ["| Property | Value |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(md)


def _team_contributions_md(run_id: str) -> str:
    """Render a per-subtask 'who did what' section from assignments + outputs."""
    db = get_db()
    subtasks = list(
        db.subtasks.find({"run_id": run_id}, {"_id": 0}).sort("topo_index", 1)
    )
    assigns = {a["subtask_id"]: a for a in
               db.assignments.find({"run_id": run_id}, {"_id": 0})}
    outputs = {o["subtask_id"]: o for o in
               db.subtask_outputs.find({"run_id": run_id}, {"_id": 0})}

    skill_names: dict[str, str] = {
        s["skill_id"]: s["name"] for s in
        db.skills.find({}, {"_id": 0, "skill_id": 1, "name": 1})
    }

    lines: list[str] = []
    for st in subtasks:
        sid = st["subtask_id"]
        a = assigns.get(sid, {})
        out = outputs.get(sid, {})
        lines.append(f"### {sid} — {st['title']}")
        contribs = a.get("contribution_scores") or []
        if contribs:
            for c in contribs:
                names = [skill_names.get(s, s) for s in c.get("skills_contributed", [])]
                names_md = ", ".join(f"_{n}_" for n in names) if names else "—"
                lines.append(
                    f"- **{c['agent_id']}** (score {c['score']:.2f}) → {names_md}"
                )
        else:
            lines.append("- _solo marshal coverage_")
        if out.get("summary"):
            lines.append("")
            lines.append(f"> {out['summary']}")
        lines.append("")
    return "\n".join(lines)


def build_report(run_id: str, prompt: str, spec: dict, validation: dict, cost: dict) -> str:
    """Assemble the final markdown report and persist it as an artifact.

    The report combines an LLM-generated introduction with deterministic
    tables (design characteristics, validation outcome, cost roll-up,
    per-subtask team contributions). Stored both as an ``artifacts`` row
    of kind ``final_report_md`` and on the ``runs`` row for convenience.

    Args:
        run_id: The active run identifier.
        prompt: The original user prompt.
        spec: The synthesised design specification.
        validation: The validation results document.
        cost: The conceptual cost estimate document.

    Returns:
        str: The full markdown report body.
    """
    intro = chat(
        render("reporter", prompt=prompt, spec=spec, validation=validation, cost=cost),
        role="reporter",
    )

    md = (
        f"# Conceptual Design Brief\n\n"
        f"{DISCLAIMER}\n\n"
        f"**Run:** `{run_id}`  \n"
        f"**Prompt:** {prompt}\n\n"
        f"## Introduction\n{intro}\n\n"
        f"## Final design characteristics\n{_design_characteristics_md(spec)}\n\n"
        f"## Validation\n- Overall: **{validation['overall_status']}**\n"
        + "\n".join(f"  - {c['name']}: {c['status']}" for c in validation['checks'])
        + f"\n\n## Cost\n- Total: **{cost['total']:,} {cost['currency']}** "
          f"(subtotal {cost['subtotal']:,}, contingency {cost['contingency_pct']}%)\n\n"
        f"## Team contributions\n{_team_contributions_md(run_id)}\n"
    )
    insert_with_event(
        "artifacts",
        {"run_id": run_id, "kind": "final_report_md", "uri_or_inline": md},
        event_kind="report_built",
    )
    get_db().runs.update_one({"run_id": run_id}, {"$set": {"final_report_md": md}})
    return md
