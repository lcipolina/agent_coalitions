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


def _bridge_characteristics_md(spec: dict) -> str:
    """Render the final bridge characteristics as a compact markdown table."""
    layout = spec.get("span_layout") or []
    spans = [s.get("length_m", 0) for s in layout]
    longest = max(spans) if spans else 0
    rows = [
        ("Bridge type", spec.get("bridge_type", "—")),
        ("Total length", f"{spec.get('total_length_m', 0)} m"),
        ("Number of spans", str(len(layout)) if layout else "—"),
        ("Longest span", f"{longest} m"),
        ("Deck width", f"{spec.get('deck_width_m', 0)} m"),
        ("Lanes", str(spec.get("lanes", "—"))),
        ("Design live load", f"{spec.get('design_live_load_kN_per_m', 0)} kN/m"),
        ("Structural depth",
         f"{spec.get('structural_depth_m', 0)} m"
         if spec.get("structural_depth_m") else "—"),
        ("Primary material", spec.get("primary_material", "—")),
        ("Deck material", spec.get("deck_material", "—")),
        ("Aesthetic style", spec.get("aesthetic_style", "—")),
    ]
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
    intro = chat(
        render("reporter", prompt=prompt, spec=spec, validation=validation, cost=cost),
        role="reporter",
    )

    md = (
        f"# Conceptual Bridge Design Brief\n\n"
        f"{DISCLAIMER}\n\n"
        f"**Run:** `{run_id}`  \n"
        f"**Prompt:** {prompt}\n\n"
        f"## Introduction\n{intro}\n\n"
        f"## Final bridge characteristics\n{_bridge_characteristics_md(spec)}\n\n"
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
