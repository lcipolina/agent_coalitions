"""Marshal: posts kickoff (round 0) and reconciles contributions (round 2)."""
from __future__ import annotations

from src.agents.blackboard import post, read
from src.llm.openai_client import chat
from src.llm.prompts import render
from src.tokens import truncate_to_tokens

MARSHAL_ID = "agent_synthetic_marshal"


def kickoff(run_id: str, subtask: dict, coalition_agent_ids: list[str],
            upstream_summaries: list[dict]) -> str:
    prompt = render(
        "marshal_kickoff",
        subtask=subtask,
        coalition_agent_ids=coalition_agent_ids,
        upstream_summaries=upstream_summaries,
    )
    text = chat(prompt, role="marshal_kickoff", subtask_id=subtask["subtask_id"])
    post(run_id, subtask["subtask_id"], MARSHAL_ID, "marshal", 0, text)
    return text


def reconcile(run_id: str, subtask: dict) -> str:
    msgs = read(run_id, subtask["subtask_id"])
    contribs = [m for m in msgs if m["role"] == "agent" and m["round"] == 1]
    prompt = render(
        "marshal_reconcile",
        subtask=subtask,
        n_contributions=len(contribs),
        contributions=contribs,
    )
    text = chat(prompt, role="marshal_reconcile", subtask_id=subtask["subtask_id"])
    post(run_id, subtask["subtask_id"], MARSHAL_ID, "marshal", 2,
         truncate_to_tokens(text, 200))
    return text
