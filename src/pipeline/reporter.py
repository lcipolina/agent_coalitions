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


def build_report(run_id: str, prompt: str, spec: dict, validation: dict, cost: dict) -> str:
    body = chat(
        render("reporter", prompt=prompt, spec=spec, validation=validation, cost=cost),
        role="reporter",
    )
    md = (
        f"# Conceptual Bridge Design Brief\n\n"
        f"{DISCLAIMER}\n\n"
        f"**Run:** `{run_id}`  \n"
        f"**Prompt:** {prompt}\n\n"
        f"## Summary\n{body}\n\n"
        f"## Validation\n- Overall: **{validation['overall_status']}**\n"
        + "\n".join(f"  - {c['name']}: {c['status']}" for c in validation['checks'])
        + f"\n\n## Cost\n- Total: **{cost['total']:,} {cost['currency']}** "
          f"(subtotal {cost['subtotal']:,}, contingency {cost['contingency_pct']}%)\n"
        f"\n## Design spec\n- Type: {spec.get('bridge_type')}\n"
        f"- Total length: {spec.get('total_length_m')} m\n"
        f"- Deck width: {spec.get('deck_width_m')} m, lanes: {spec.get('lanes')}\n"
        f"- Primary material: {spec.get('primary_material')}\n"
        f"- Aesthetic: {spec.get('aesthetic_style')}\n"
    )
    insert_with_event(
        "artifacts",
        {"run_id": run_id, "kind": "final_report_md", "uri_or_inline": md},
        event_kind="report_built",
    )
    get_db().runs.update_one({"run_id": run_id}, {"$set": {"final_report_md": md}})
    return md
