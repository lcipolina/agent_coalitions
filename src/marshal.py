"""Marshal: posts kickoff (round 0) and reconciles contributions (round 2)."""
from __future__ import annotations

from src.blackboard import post, read
from src.llm.openai_client import chat
from src.tokens import truncate_to_tokens

MARSHAL_ID = "agent_synthetic_marshal"


def kickoff(run_id: str, subtask: dict, coalition_agent_ids: list[str],
            upstream_summaries: list[dict]) -> str:
    upstream_text = "\n".join(
        f"- {u['subtask_id']}: {u['summary']}" for u in upstream_summaries
    ) or "(none)"
    prompt = (
        f"Subtask {subtask['subtask_id']} ({subtask['title']}): {subtask['description']}\n"
        f"Coalition agents: {', '.join(coalition_agent_ids)}\n"
        f"Upstream summaries:\n{upstream_text}"
    )
    text = chat(prompt, role="marshal_kickoff", subtask_id=subtask["subtask_id"])
    post(run_id, subtask["subtask_id"], MARSHAL_ID, "marshal", 0, text)
    return text


def reconcile(run_id: str, subtask: dict) -> str:
    msgs = read(run_id, subtask["subtask_id"])
    contribs = [m for m in msgs if m["role"] == "agent" and m["round"] == 1]
    prompt = (
        f"Reconcile {len(contribs)} contributions for subtask "
        f"{subtask['subtask_id']} ({subtask['title']}). "
        f"Produce a unified summary and structured fields."
    )
    text = chat(prompt, role="marshal_reconcile", subtask_id=subtask["subtask_id"])
    post(run_id, subtask["subtask_id"], MARSHAL_ID, "marshal", 2,
         truncate_to_tokens(text, 200))
    return text
