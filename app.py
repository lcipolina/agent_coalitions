"""Streamlit demo UI for the Agent Coalitions bridge-design pipeline.

Run:
    streamlit run app.py

Default mode is mock (USE_MOCK_LLM=true). For the demo this should finish a
full run in <5 seconds while showing live progress: skills selected per
subtask, agents picked + their solo scores, who paired with whom, and a
TQDM-style progress bar across the 8 pipeline stages.
"""
from __future__ import annotations

import os
import time
from typing import Any

# Default to mock mode for the live demo (judges have ~2-3 minutes).
os.environ.setdefault("USE_MOCK_LLM", "true")

import streamlit as st  # noqa: E402

from src.config import settings  # noqa: E402
from src.db.client import get_db  # noqa: E402
from src.pipeline.orchestrator import replay, run_pipeline  # noqa: E402
from src.progress import set_listener  # noqa: E402

st.set_page_config(
    page_title="Agent Coalitions — Bridge Design",
    page_icon="🌉",
    layout="wide",
)

DEFAULT_PROMPT = "design a 2 km bridge for 50 cars/h with trucks, modern aesthetic"

STAGES = [
    ("decompose", "1️⃣  Decompose"),
    ("execute", "2️⃣  Coalitions & blackboard"),
    ("synthesise", "3️⃣  Synthesise spec"),
    ("validate", "4️⃣  Validate"),
    ("estimate", "5️⃣  Cost"),
    ("report", "6️⃣  Report"),
    ("reputation", "7️⃣  Reputation"),
]


# ----------------------------------------------------------------------------
# Session state init
# ----------------------------------------------------------------------------
def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("run_id", None)
    ss.setdefault("running", False)
    ss.setdefault("events", [])  # list of (kind, info)


_init_state()


# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️  Mode")
    st.write(f"**Mock LLM:** `{settings.use_mock_llm}`")
    st.write(f"**Mongo DB:** `{settings.mongodb_db}`")
    st.caption(
        "Mock mode is the default for the live demo. Toggle real mode "
        "by setting `USE_MOCK_LLM=false` in `.env` and restarting Streamlit."
    )
    st.divider()
    st.header("📜  History")
    db = get_db()
    recent = list(
        db.runs.find({}, {"_id": 0, "run_id": 1, "prompt": 1, "status": 1,
                          "summary_metrics": 1})
        .sort("started_at", -1).limit(10)
    )
    for r in recent:
        label = f"`{r['run_id']}` — {r.get('status', '?')}"
        if st.button(label, key=f"hist_{r['run_id']}", use_container_width=True):
            st.session_state.run_id = r["run_id"]
            st.session_state.running = False
            st.rerun()


# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
st.title("🌉  Agent Coalitions — Bridge Design")
st.caption(
    "Multi-agent coalition formation over a MongoDB Atlas Vector Search "
    "skills index. Mock mode is fully deterministic and runs in seconds."
)

prompt = st.text_input("Design prompt", value=DEFAULT_PROMPT)
run_col, replay_col, _ = st.columns([1, 1, 4])
run_clicked = run_col.button("🚀  Run pipeline", type="primary",
                             disabled=st.session_state.running)
replay_clicked = replay_col.button(
    "🔁  Replay current",
    disabled=st.session_state.running or st.session_state.run_id is None,
)


# ----------------------------------------------------------------------------
# Live run view
# ----------------------------------------------------------------------------
def _live_listener_factory(
    progress_bar,
    stage_status,
    subtask_box,
    skill_box,
    log_area,
):
    """Return a callback that updates Streamlit widgets in place."""
    state: dict[str, Any] = {
        "stages_done": 0,
        "n_subtasks": 0,
        "subtasks_done": 0,
        "stage_starts": {},
    }
    n_stages = len(STAGES)

    def cb(kind: str, info: dict[str, Any]) -> None:
        st.session_state.events.append((kind, info))

        if kind == "pipeline_start":
            stage_status.info(f"Starting run for: *{info.get('prompt')}*")

        elif kind == "stage_start":
            stage = info["stage"]
            state["stage_starts"][stage] = time.time()
            label = next((lbl for s, lbl in STAGES if s == stage), stage)
            stage_status.info(f"⏳  {label} …")

        elif kind == "decomposed":
            state["n_subtasks"] = info["n_subtasks"]
            lines = "\n".join(
                f"- **{s['id']}** — {s['title']}"
                + (f"  ←  {', '.join(s['deps'])}" if s["deps"] else "")
                for s in info["subtasks"]
            )
            log_area.markdown(f"**DAG ({info['n_subtasks']} subtasks):**\n{lines}")

        elif kind == "subtask_start":
            subtask_box.markdown(
                f"### 🎯  {info['subtask_id']} — {info['title']}  "
                f"`({info['idx']}/{info['total']})`"
            )
            skill_box.empty()

        elif kind == "candidates_found":
            skill_box.caption(
                f"🔎  {info['n']} candidate skills retrieved from vector search"
            )

        elif kind == "coalition_formed":
            skills_md = "\n".join(
                f"  - `{s['skill_id']}` — *{s['name']}*  "
                f"(solo {s['solo']:.2f})"
                for s in info["skills"]
            )
            agents_md = "\n".join(
                f"  - 🤖  **{a['agent_id']}**  score `{a['score']:.2f}`  "
                f"→ skills: {', '.join(a['skills_contributed']) or '—'}"
                for a in info["agents"]
            )
            skill_box.markdown(
                f"**Coalition formed.**\n\n"
                f"**Skills picked:**\n{skills_md}\n\n"
                f"**Agents assigned (set-cover):**\n{agents_md}\n\n"
                f"_Rationale:_ {info['rationale']}"
            )

        elif kind == "round_posted":
            # Lightweight ticker append.
            pass

        elif kind == "subtask_end":
            state["subtasks_done"] += 1

        elif kind == "stage_end":
            state["stages_done"] += 1
            frac = state["stages_done"] / n_stages
            progress_bar.progress(min(frac, 1.0))

        elif kind == "pipeline_end":
            progress_bar.progress(1.0)
            stage_status.success(
                f"✅  Pipeline complete — `{info['summary']['run_id']}`"
            )

    return cb


if run_clicked:
    st.session_state.events = []
    st.session_state.running = True
    with st.container(border=True):
        st.subheader("🏃  Live progress")
        progress_bar = st.progress(0.0)
        stage_status = st.empty()
        subtask_box = st.empty()
        skill_box = st.empty()
        log_area = st.empty()

        cb = _live_listener_factory(
            progress_bar, stage_status, subtask_box, skill_box, log_area,
        )
        try:
            with set_listener(cb):
                summary = run_pipeline(prompt)
            st.session_state.run_id = summary["run_id"]
        except Exception as e:  # noqa: BLE001
            stage_status.error(f"Pipeline failed: {e}")
            raise
        finally:
            st.session_state.running = False

if replay_clicked and st.session_state.run_id:
    with st.spinner("Replaying from MongoDB (no LLM calls)…"):
        rep = replay(st.session_state.run_id)
    st.success(f"Replay OK — counters: {rep}")


# ----------------------------------------------------------------------------
# Tabs (only meaningful once a run_id exists)
# ----------------------------------------------------------------------------
if st.session_state.run_id is None:
    st.info("Click **Run pipeline** above to start. Default prompt is "
            "pre-filled. The 8 tabs below populate from MongoDB once a "
            "run completes.")
    st.stop()

run_id = st.session_state.run_id
db = get_db()
run_doc = db.runs.find_one({"run_id": run_id}, {"_id": 0}) or {}
st.markdown(f"### Current run: `{run_id}`")
metrics = run_doc.get("summary_metrics") or {}
if metrics:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Subtasks", metrics.get("n_subtasks", "—"))
    c2.metric("Messages", metrics.get("n_messages", "—"))
    c3.metric("Validation", metrics.get("validation_status", "—"))
    cost = metrics.get("estimated_cost_eur")
    c4.metric("Cost (EUR)", f"{cost:,.0f}" if isinstance(cost, (int, float)) else "—")

(
    tab_dag, tab_coal, tab_bb, tab_val, tab_cost, tab_bridge, tab_report, tab_reput,
) = st.tabs([
    "🌳 DAG", "🤝 Coalitions", "💬 Blackboard", "✅ Validation",
    "💶 Cost", "🌉 Bridge", "📄 Report", "📈 Reputation",
])


# ----- DAG ------------------------------------------------------------------
with tab_dag:
    subtasks = list(
        db.subtasks.find({"run_id": run_id}, {"_id": 0}).sort("topo_index", 1)
    )
    if not subtasks:
        st.info("No subtasks yet.")
    else:
        lines = ["digraph G {", '  rankdir=LR; node [shape=box, style=rounded];']
        for s in subtasks:
            lines.append(
                f'  {s["subtask_id"]} '
                f'[label="{s["subtask_id"]}\\n{s["title"]}\\n[{s["status"]}]"];'
            )
        for s in subtasks:
            for dep in s.get("depends_on", []):
                lines.append(f"  {dep} -> {s['subtask_id']};")
        lines.append("}")
        st.graphviz_chart("\n".join(lines))
        st.dataframe(
            [{
                "id": s["subtask_id"], "title": s["title"],
                "deps": ", ".join(s.get("depends_on", [])),
                "status": s["status"],
                "capabilities": ", ".join(s.get("required_capabilities", [])),
            } for s in subtasks],
            use_container_width=True, hide_index=True,
        )


# ----- Coalitions -----------------------------------------------------------
with tab_coal:
    assigns = list(db.assignments.find({"run_id": run_id}, {"_id": 0}))
    if not assigns:
        st.info("No assignments yet.")
    else:
        for a in assigns:
            with st.expander(
                f"{a['subtask_id']}  ·  agents: "
                f"{', '.join(a['coalition_agent_ids'])}",
                expanded=False,
            ):
                st.markdown("**Skills selected**")
                skill_docs = list(db.skills.find(
                    {"skill_id": {"$in": a["coalition_skill_ids"]}},
                    {"_id": 0, "skill_id": 1, "name": 1, "category": 1,
                     "prior_reputation": 1, "weekly_installs": 1},
                ))
                st.dataframe(skill_docs, use_container_width=True, hide_index=True)
                st.markdown("**Agent contributions**")
                st.dataframe(
                    a.get("contribution_scores", []),
                    use_container_width=True, hide_index=True,
                )
                st.caption(f"_Rationale:_ {a.get('selection_rationale', '')}")


# ----- Blackboard -----------------------------------------------------------
with tab_bb:
    msgs = list(
        db.coalition_messages.find({"run_id": run_id}, {"_id": 0})
        .sort([("subtask_id", 1), ("round", 1), ("ts", 1)])
    )
    if not msgs:
        st.info("No messages yet.")
    else:
        last_st = None
        for m in msgs:
            if m["subtask_id"] != last_st:
                st.markdown(f"#### {m['subtask_id']}")
                last_st = m["subtask_id"]
            avatar = "🧭" if m["role"] == "marshal" else "🤖"
            with st.chat_message("assistant", avatar=avatar):
                st.markdown(
                    f"**{m['sender']}**  ·  round {m['round']}  ·  "
                    f"_{m['role']}_"
                )
                st.write(m["text"])


# ----- Validation -----------------------------------------------------------
with tab_val:
    v = db.validation_results.find_one({"run_id": run_id}, {"_id": 0})
    if not v:
        st.info("No validation yet.")
    else:
        status = v["overall_status"]
        if status == "conceptual_pass":
            st.success(f"Overall: **{status}**")
        elif status == "conceptual_pass_with_warnings":
            st.warning(f"Overall: **{status}**")
        else:
            st.error(f"Overall: **{status}**")
        st.dataframe(v["checks"], use_container_width=True, hide_index=True)
        st.markdown("#### Judge scores per subtask")
        st.dataframe(v.get("judge_scores", []),
                     use_container_width=True, hide_index=True)


# ----- Cost -----------------------------------------------------------------
with tab_cost:
    c = db.cost_estimates.find_one({"run_id": run_id}, {"_id": 0})
    if not c:
        st.info("No cost estimate yet.")
    else:
        st.metric(f"Total ({c['currency']})", f"{c['total']:,}")
        st.dataframe(c["line_items"], use_container_width=True, hide_index=True)
        st.caption(
            f"Subtotal {c['subtotal']:,} + finishing {c['finishing_premium_pct']}% "
            f"+ contingency {c['contingency_pct']}%"
        )
        st.markdown(f"> {c['narrative']}")


# ----- Bridge visualisation ------------------------------------------------
with tab_bridge:
    spec = db.design_specs.find_one({"run_id": run_id}, {"_id": 0})
    if not spec:
        st.info("No design spec yet.")
    else:
        import plotly.graph_objects as go

        layout = spec.get("span_layout") or []
        L = spec.get("total_length_m", sum(s.get("length_m", 0) for s in layout))
        depth = spec.get("structural_depth_m") or max((max(
            (s.get("length_m", 0) for s in layout), default=0
        ) / 12.0), 1.0)
        deck_y = depth
        x_supports = [0.0]
        x = 0.0
        for s in layout:
            x += s.get("length_m", 0)
            x_supports.append(x)

        fig = go.Figure()
        # Deck
        fig.add_trace(go.Scatter(
            x=[0, L], y=[deck_y, deck_y], mode="lines",
            line=dict(width=8, color="#444"), name="deck",
        ))
        # Piers
        for xp in x_supports:
            fig.add_trace(go.Scatter(
                x=[xp, xp], y=[0, deck_y], mode="lines",
                line=dict(width=4, color="#888"), showlegend=False,
            ))
        # Water
        fig.add_shape(
            type="rect", x0=0, x1=L, y0=-2, y1=0,
            fillcolor="rgba(80,140,200,0.25)", line_width=0,
        )
        fig.update_layout(
            height=320,
            xaxis_title="Distance along bridge (m)",
            yaxis_title="Elevation (m)",
            yaxis=dict(scaleanchor="x", scaleratio=4),
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.json(spec, expanded=False)


# ----- Report ---------------------------------------------------------------
with tab_report:
    art = db.artifacts.find_one(
        {"run_id": run_id, "kind": "final_report_md"}, {"_id": 0},
    )
    if not art:
        st.info("No report yet.")
    else:
        st.markdown(art["uri_or_inline"])


# ----- Reputation -----------------------------------------------------------
with tab_reput:
    deltas = list(
        db.reputation_updates.find({"run_id": run_id}, {"_id": 0})
    )
    if not deltas:
        st.info("No reputation updates yet.")
    else:
        st.dataframe(deltas, use_container_width=True, hide_index=True)
        st.caption(
            "Cumulative reputations across all runs are stored on each agent "
            "row (see Mongo `agents` collection). G10 verifies persistence."
        )
        agent_ids = [d["agent_id"] for d in deltas]
        agent_docs = list(db.agents.find(
            {"agent_id": {"$in": agent_ids}},
            {"_id": 0, "agent_id": 1, "reputation": 1,
             "runs_participated": 1, "runs_succeeded": 1},
        ))
        st.markdown("#### Cumulative reputation (across all runs)")
        st.dataframe(agent_docs, use_container_width=True, hide_index=True)
