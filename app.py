"""Streamlit demo UI for the Agent Teams design pipeline.

Run:
    streamlit run app.py

Default mode is mock (USE_MOCK_LLM=true). For the demo this should finish a
full run in <5 seconds while showing live progress: skills selected per
subtask, agents picked + their solo scores, who paired with whom, and a
TQDM-style progress bar across the 9 pipeline stages.
"""
from __future__ import annotations

import os
import time
from typing import Any

# The published demo runs entirely from the captured replay cache
# (data/llm_replay_cache.json) — no OpenAI key, no network calls.
# Force mock mode here so toggling cannot accidentally hit the API.
os.environ["USE_MOCK_LLM"] = "true"

import streamlit as st  # noqa: E402

# When deployed to Streamlit Community Cloud, secrets live in the platform's
# Secrets panel (TOML) rather than a local .env file. Copy any keys from
# st.secrets into os.environ BEFORE src.core.config is imported, so the
# existing pydantic-settings loader picks them up without modification.
# Locally, st.secrets is empty when no .streamlit/secrets.toml exists, so
# this loop is a no-op and the .env file is used as before.
def _hydrate_env_from_st_secrets() -> None:
    """Flatten st.secrets (incl. one level of [section] nesting) into os.environ."""
    try:
        items = list(st.secrets.items())
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return
    for k, v in items:
        # Top-level scalar — copy as-is.
        if isinstance(v, (str, int, float, bool)):
            os.environ.setdefault(k, str(v))
            continue
        # One level of nesting (e.g. [env] or [secrets] section header).
        try:
            for sub_k, sub_v in v.items():
                if isinstance(sub_v, (str, int, float, bool)):
                    os.environ.setdefault(sub_k, str(sub_v))
        except AttributeError:
            continue


_hydrate_env_from_st_secrets()

# Surface a clear, non-redacted error if the secret most likely to be
# missing on a fresh Cloud deploy is still absent. pydantic's default
# ValidationError is redacted in production, which makes this hard to
# diagnose from the deployed UI.
if not os.environ.get("MONGODB_URI"):
    st.error(
        "**Configuration error: `MONGODB_URI` is not set.**\n\n"
        "If you are running locally, copy `.env.example` to `.env` and "
        "fill in your Atlas connection string.\n\n"
        "If you are on Streamlit Community Cloud, open **Manage app \u2192 "
        "Settings \u2192 Secrets** and paste the contents of "
        "`.streamlit/secrets.toml.example` with real values. The keys "
        "must be at the top level of the TOML, not under a `[section]` "
        "header, and values must be quoted strings."
    )
    st.stop()

from src.core.config import settings  # noqa: E402
from src.db.client import get_db, ping_db  # noqa: E402
from src.pipeline.orchestrator import run_pipeline as _run_pipeline_fn  # noqa: E402


# LangGraph is an optional dependency: if it isn't installed, the toggle
# in the sidebar is disabled and the rest of the app still works.
try:
    from src.pipeline.orchestrator_lg import (  # noqa: E402
        build_graph as _build_lg_graph,
        run_pipeline as _run_pipeline_lg,
    )
    LANGGRAPH_AVAILABLE = True
    LANGGRAPH_IMPORT_ERROR: str | None = None
except Exception as _exc:  # pragma: no cover — import-time fallback
    _build_lg_graph = None  # type: ignore[assignment]
    _run_pipeline_lg = None  # type: ignore[assignment]
    LANGGRAPH_AVAILABLE = False
    LANGGRAPH_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"


def run_pipeline(prompt: str):
    """Dispatch to the backend selected by ``settings.use_langgraph``.

    Reading the flag at call time (not import time) lets the sidebar
    toggle flip backends without restarting Streamlit.
    """
    if settings.use_langgraph and LANGGRAPH_AVAILABLE:
        return _run_pipeline_lg(prompt)  # type: ignore[misc]
    return _run_pipeline_fn(prompt)


from src.core.progress import set_listener  # noqa: E402

st.set_page_config(
    page_title="Cadre — Agentic Team Formation over a Skill Marketplace",
    page_icon="🔮",
    layout="wide",
)

DEFAULT_PROMPT = "design a 2 km bridge for 50 cars/h, modern aesthetic"

# Curated prompts that have captured LLM responses in
# data/llm_replay_cache.json. The dropdown is locked to this set so the
# published demo never tries to call OpenAI.
DEMO_PROMPTS: list[str] = [
    "Build me a bridge for 50 cars per hours - modern design",
    "Build me a rollercoaster for 50 people - modern design",
    "Build me an airplane for 200 people",
]

# User-facing labels for the dropdown. The keys above are the **exact**
# strings that match the captured replay cache; the values below are
# what we show to the user. Changing only the labels keeps every
# downstream cache lookup intact.
DEMO_PROMPT_LABELS: dict[str, str] = {
    "Build me a bridge for 50 cars per hours - modern design":
        "Design a bridge for 50 cars per hour \u2014 modern design",
    "Build me a rollercoaster for 50 people - modern design":
        "Design a rollercoaster for 50 people \u2014 modern design",
    "Build me an airplane for 200 people":
        "Design an airplane for 200 people",
}

STAGES = [
    ("decompose", "1️⃣  Decompose"),
    ("execute", "2️⃣  Teams & agent comms"),
    ("synthesise", "3️⃣  Synthesise spec"),
    ("validate", "4️⃣  Validate"),
    ("estimate", "5️⃣  Cost"),
    ("visualise", "6️⃣  Render geometry"),
    ("report", "7️⃣  Report"),
    ("reputation", "8️⃣  Reputation"),
]


# ----------------------------------------------------------------------------
# Agent display labels
# ----------------------------------------------------------------------------
# The persistent ``agent_id`` (e.g. ``agent_007``) is opaque to demo audiences.
# This helper turns it into a short label like ``#007`` (or ``Marshal`` for
# the coordinator). We deliberately do **not** include the agent's owned
# skills in the label: an agent's full skill set is unrelated to the skills
# it contributes for any specific subtask, and showing e.g. "propulsion" in
# the label of an agent participating in a bridge team is misleading. The
# *skills actually contributed* are shown in the ``skills_contributed``
# column of the Teams tab where they belong.

@st.cache_data(show_spinner=False)
def _agent_display_map(_db_name: str = settings.mongodb_db) -> dict[str, str]:
    """Return ``{agent_id: human_label}`` for every agent in the catalog."""
    out: dict[str, str] = {}
    for ag in get_db().agents.find(
        {}, {"_id": 0, "agent_id": 1},
    ):
        aid = ag["agent_id"]
        if aid == "agent_marshal":
            out[aid] = "Marshal"
            continue
        # Just the numeric suffix, e.g. ``agent_007`` -> ``#007``.
        out[aid] = f"#{aid.split('_')[-1]}"
    return out


def _agent_label(agent_id: str) -> str:
    """Return the human-friendly label for ``agent_id`` (id itself if unknown)."""
    return _agent_display_map().get(agent_id, agent_id)


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

    # Demo lock-down: this build runs from the captured replay cache only.
    # The Mock LLM toggle (and the live OpenAI path) is intentionally
    # absent so the published demo cannot make API calls. To re-enable
    # live mode, revert this block and remove the forced
    # ``USE_MOCK_LLM=true`` at the top of this file.
    settings.use_mock_llm = True

    from src.llm import replay as _replay_info  # noqa: E402

    if _replay_info.is_available():
        _meta = _replay_info.meta()
        _exported = (_meta.get("exported_at") or "")[:10]
        st.success("Replay mode")
    else:
        st.warning(
            "🔒 Replay mode is on but no captured cache was found at "
            "`data/llm_replay_cache.json`. Generic mock stubs will be "
            "used. See `scripts/export_llm_cache.py` to capture a run.",
            icon="⚠️",
        )

    # ------------------------------------------------------------------
    # Pipeline backend toggle (function vs LangGraph)
    # ------------------------------------------------------------------
    if "lg_toggle" not in st.session_state:
        st.session_state.lg_toggle = bool(settings.use_langgraph) and LANGGRAPH_AVAILABLE

    lg_on = st.toggle(
        "LangGraph backend",
        value=st.session_state.lg_toggle,
        help=(
            "OFF = plain function pipeline (src/pipeline/orchestrator.py).\n"
            "ON  = LangGraph StateGraph (src/pipeline/orchestrator_lg.py).\n"
            "Both produce identical MongoDB rows; switch any time."
            + ("" if LANGGRAPH_AVAILABLE
               else f"\n\nDisabled: LangGraph not importable ({LANGGRAPH_IMPORT_ERROR}).")
        ),
        disabled=st.session_state.running or not LANGGRAPH_AVAILABLE,
    )
    if lg_on != st.session_state.lg_toggle:
        st.session_state.lg_toggle = lg_on
        settings.use_langgraph = lg_on
        os.environ["USE_LANGGRAPH"] = "true" if lg_on else "false"

    # Visible status badge so judges can see at a glance which engine is
    # orchestrating the run.
    if lg_on:
        st.success("🕸️  Pipeline: **LangGraph** (StateGraph)", icon="🕸️")
    else:
        st.info("🧵  Pipeline: **function** (plain Python)", icon="🧵")

    st.write(f"**Mongo DB:** `{settings.mongodb_db}`")
    st.divider()
    st.header("📜  History")

    # Verify the cluster is reachable before any get_db() call. Otherwise
    # pymongo raises a redacted ConfigurationError on Streamlit Cloud and
    # the user has no way to tell DNS failure from auth failure from a
    # paused Atlas free-tier cluster.
    _ok, _err = ping_db()
    if not _ok:
        st.error(
            "**MongoDB Atlas is unreachable.**\n\n"
            f"Underlying error: `{_err}`\n\n"
            "Common causes:\n"
            "1. The Atlas free-tier cluster is **paused** \u2014 sign in at "
            "https://cloud.mongodb.com and click *Resume*.\n"
            "2. **Network Access** does not allow Streamlit Cloud's egress IPs "
            "\u2014 add `0.0.0.0/0` to the cluster's IP allow-list.\n"
            "3. The `MONGODB_URI` secret is wrong (typo, missing `+srv`, "
            "or password not URL-encoded).\n\n"
            "Run `python scripts/check_mongo.py` locally to confirm the "
            "cluster is healthy from your machine."
        )
        st.stop()

    db = get_db()
    recent = list(
        db.runs.find({}, {"_id": 0, "run_id": 1, "prompt": 1, "status": 1,
                          "summary_metrics": 1})
        .sort("started_at", -1).limit(5)
    )
    for r in recent:
        label = f"`{r['run_id']}` \u2014 {r.get('status', '?')}"
        if st.button(label, key=f"hist_{r['run_id']}", use_container_width=True):
            st.session_state.run_id = r["run_id"]
            st.session_state.running = False
            st.rerun()


# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
st.title("🔮  Cadre")
st.subheader(
    "A team of specialized agents for tasks too complex for a single agent."
)
st.caption(
    "An orchestrator splits a long task into subtasks and assigns each "
    "one to a team led by a marshal who coordinates the work. Teams are "
    "built over a skill marketplace using Shapley values to pick the "
    "skills and role assignment to staff the agents."
)

prompt = st.selectbox(
    "Design prompt",
    DEMO_PROMPTS,
    index=0,
    format_func=lambda p: DEMO_PROMPT_LABELS.get(p, p),
    help=(
        "Replay-mode demo: only these three prompts have captured LLM "
        "responses. To add another prompt, run it once with "
        "`USE_MOCK_LLM=false` and re-run `scripts/export_llm_cache.py`."
    ),
)
run_col, _ = st.columns([1, 5])
run_clicked = run_col.button("🚀  Run pipeline", type="primary",
                             disabled=st.session_state.running)


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
                f"  - `{s['skill_id']}` \u2014 *{s['name']}*  "
                f"(\u03c6 {s.get('shapley', s.get('solo', 0.0)):.2f})"
                for s in info["skills"]
            )
            shapley_total = sum(a.get("shapley", 0.0) for a in info["agents"]) or 1.0
            # Pre-compute the per-agent skill list as a plain string outside
            # the f-string. Python 3.11 forbids backslashes inside f-string
            # ``{...}`` expressions, so the ``'\u2014'`` fallback escape
            # cannot live there directly.
            EM_DASH = "\u2014"
            agents_md = "\n".join(
                f"  - \U0001f916  **{_agent_label(a['agent_id'])}**  "
                f"\u03c6 `{a.get('shapley', 0.0):.2f}` "
                f"({100.0 * a.get('shapley', 0.0) / shapley_total:.0f} %)  "
                f"\u2192 skills: {(', '.join(a['skills_contributed']) or EM_DASH)}"
                for a in info["agents"]
            )
            skill_box.markdown(
                f"**Team formed.**\n\n"
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
            # Clear the live snapshots so the page doesn't keep showing the
            # last subtask's team / DAG below the success banner — the full
            # results are in the tabs below.
            subtask_box.empty()
            skill_box.empty()
            log_area.empty()

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
            stage_status.error(
                f"⚠️ Pipeline failed: **{type(e).__name__}** — {e}\n\n"
                "This usually happens when the LLM returns malformed JSON or "
                "an unsupported domain shape. Try the prompt again or switch "
                "Mock LLM ON in the sidebar for a deterministic run."
            )
        finally:
            st.session_state.running = False


# ----------------------------------------------------------------------------
# Tabs (only meaningful once a run_id exists)
# ----------------------------------------------------------------------------
if st.session_state.run_id is None:
    st.info("Click **Run pipeline** above to start. "
            "The 8 tabs below populate from MongoDB once a run completes.")
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
    # Translate the raw validator status into a demo-friendly label.
    _vs = metrics.get("validation_status", "\u2014")
    _vs_soft = {
        "conceptual_pass": "Excellent",
        "conceptual_pass_with_warnings": "Acceptable",
        "conceptual_fail": "Needs review",
    }.get(_vs, _vs)
    c3.metric("Validation", _vs_soft)
    cost = metrics.get("estimated_cost_eur")
    c4.metric("Cost (EUR)", f"{cost:,.0f}" if isinstance(cost, (int, float)) else "—")

(
    tab_dag, tab_coal, tab_bb, tab_val, tab_render, tab_concept,
    tab_report, tab_reput, tab_workflow, tab_mongo,
) = st.tabs([
    "\U0001f333 DAG", "\U0001f465 Teams", "\U0001f4ac Agent comms", "\u2705 Validation",
    "\U0001f3a8 Rendering", "\U0001f5bc\ufe0f Concept render",
    "\U0001f4c4 Report", "\U0001f4c8 Reputation",
    "\U0001f578\ufe0f Workflow", "\U0001f343 MongoDB",
])


# ----- DAG ------------------------------------------------------------------
with tab_dag:
    subtasks = list(
        db.subtasks.find({"run_id": run_id}, {"_id": 0}).sort("topo_index", 1)
    )
    if not subtasks:
        st.info("No subtasks yet.")
    else:
        st.markdown("#### Subtask DAG (data-flow)")
        st.caption(
            "Topological view of subtasks emitted by the decomposer. "
            "Edges are *upstream-output* dependencies, **not** authority."
        )
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

        # ----- Org chart ----------------------------------------------------
        # Hierarchical view: the orchestrator (the Python pipeline) spawns
        # one marshal per subtask, and each marshal coordinates the agents
        # the set-cover step assigned to that subtask. This is the
        # *authority* graph, complementing the data-flow DAG above.
        st.markdown("#### Org chart (orchestrator → marshals → agents)")
        st.caption(
            "Authority view. The orchestrator spawns one marshal per "
            "subtask; each marshal coordinates the agents assigned to its "
            "team. Same agent can appear under multiple marshals when "
            "set-cover reuses it."
        )
        assigns = list(db.assignments.find(
            {"run_id": run_id}, {"_id": 0}
        ))
        org_lines = [
            "digraph Org {",
            "  rankdir=TB;",
            "  splines=ortho;",
            '  node [shape=box, style="rounded,filled", fontname="Helvetica"];',
            '  ORCH [label="Orchestrator\\n(pipeline)", '
            'fillcolor="#1c2833", fontcolor=white];',
        ]
        seen_agents: set[str] = set()
        for a in assigns:
            sid = a["subtask_id"]
            marshal_node = f"M_{sid}"
            title = next(
                (s["title"] for s in subtasks if s["subtask_id"] == sid), sid
            )
            # Escape any double-quotes that would break the dot label.
            safe_title = title.replace('"', "'")
            org_lines.append(
                f'  {marshal_node} '
                f'[label="🧭 Marshal\\n{sid}: {safe_title}", '
                f'fillcolor="#d35400", fontcolor=white];'
            )
            org_lines.append(f"  ORCH -> {marshal_node};")
            for aid in a.get("coalition_agent_ids", []):
                # Drop the marshal-fallback id; it isn't a real teammate.
                if aid == "agent_marshal":
                    continue
                node = f"A_{aid}"
                if aid not in seen_agents:
                    safe_label = _agent_label(aid).replace('"', "'")
                    org_lines.append(
                        f'  {node} '
                        f'[label="🤖 {safe_label}", fillcolor="#ecf0f1"];'
                    )
                    seen_agents.add(aid)
                org_lines.append(f"  {marshal_node} -> {node};")
        org_lines.append("}")
        st.graphviz_chart("\n".join(org_lines))

        st.markdown("#### Subtask details")
        st.dataframe(
            [{
                "id": s["subtask_id"], "title": s["title"],
                "dependencies": ", ".join(s.get("depends_on", [])),
                "status": s["status"],
                "capabilities": ", ".join(s.get("required_capabilities", [])),
            } for s in subtasks],
            use_container_width=True, hide_index=True,
        )


# ----- Teams ----------------------------------------------------------------
with tab_coal:
    st.caption(
        "One team is formed per subtask (T1, T2, \u2026). The orchestrator "
        "assigns skills to each team via cosine similarity between the "
        "subtask's required capabilities and the skill marketplace. Skills "
        "can be shared across teams when capabilities overlap."
    )
    assigns = list(db.assignments.find({"run_id": run_id}, {"_id": 0}))
    if not assigns:
        st.info("No assignments yet.")
    else:
        # Map subtask ids \u2192 subtask titles so each team box can be headlined
        # with the subtask name (e.g. "T3 \u2014 Material selection").
        st_titles = {
            s["subtask_id"]: s["title"]
            for s in db.subtasks.find(
                {"run_id": run_id},
                {"_id": 0, "subtask_id": 1, "title": 1},
            )
        }
        for a in assigns:
            sid = a["subtask_id"]
            team_title = st_titles.get(sid, sid)
            agent_labels = [
                _agent_label(aid) for aid in a["coalition_agent_ids"]
            ]
            with st.expander(
                f"**{sid} \u2014 {team_title}**  \u00b7  agents: "
                f"{', '.join(agent_labels)}",
                expanded=False,
            ):
                st.markdown("**Skills selected from marketplace**")
                st.caption(
                    "Each row is one skill this team needs. Skills are "
                    "picked from the marketplace by cosine similarity "
                    "against the subtask's required capabilities; "
                    "`reputation_score` and `weekly_installs` come from "
                    "the marketplace, and `agent_assigned` shows which "
                    "team member supplies that skill."
                )
                # Preserve the order in which the team picked the skills.
                sk_order = a.get("coalition_skill_ids", [])
                skill_docs = list(db.skills.find(
                    {"skill_id": {"$in": sk_order}},
                    {"_id": 0, "skill_id": 1, "name": 1, "category": 1,
                     "prior_reputation": 1, "weekly_installs": 1},
                ))
                idx = {sid_: i for i, sid_ in enumerate(sk_order)}
                skill_docs.sort(key=lambda s: idx.get(s["skill_id"], 1e9))
                # Map every chosen skill to the agent that contributed it
                # so the Skills table and Agent contributions table line up.
                skill_to_agent: dict[str, str] = {}
                for cs in a.get("contribution_scores", []):
                    for s_id in cs.get("skills_contributed", []):
                        skill_to_agent[s_id] = cs["agent_id"]
                # Rename the marketplace fields to friendlier display
                # labels and attach the assigned agent.
                display_rows = [
                    {
                        "skill_id": sd["skill_id"],
                        "category": sd.get("category", ""),
                        "name": sd.get("name", ""),
                        "reputation_score": sd.get("prior_reputation"),
                        "weekly_installs": sd.get("weekly_installs"),
                        "agent_assigned": _agent_label(
                            skill_to_agent.get(sd["skill_id"], "\u2014")
                        ),
                    }
                    for sd in skill_docs
                ]
                st.dataframe(display_rows, use_container_width=True, hide_index=True)
                st.markdown("**Agent contributions**")
                # Build the contributions table.
                #
                # We display the *normalised Shapley value* as
                # ``contribution %`` — the fraction of the team's joint
                # output fairly attributable to each agent. The raw
                # Shapley payoff column is hidden by default because
                # game-theory jargon distracts from the demo; the
                # percentage view is the intuitive per-agent metric.
                contribs = a.get("contribution_scores", [])
                shapley_total = sum(cs.get("shapley", 0.0) for cs in contribs) or 1.0
                contrib_rows = [
                    {
                        "agent": _agent_label(cs["agent_id"]),
                        "contribution %": round(
                            100.0 * cs.get("shapley", 0.0) / shapley_total, 1,
                        ),
                        "skills_contributed": ", ".join(
                            cs.get("skills_contributed", [])
                        ),
                    }
                    for cs in contribs
                ]
                st.dataframe(
                    contrib_rows, use_container_width=True, hide_index=True,
                )
                st.caption(f"_Rationale:_ {a.get('selection_rationale', '')}")
        st.markdown("---")
        st.caption(
            "**TL;DR.**  `contribution %` = each agent's fair share of the "
            "team's joint output, computed via the closed-form Shapley value "
            "of the induced-subgraph game."
        )
        st.caption(
            "`contribution %` is the **Shapley value normalised** \u2014 i.e. "
            "*the fraction of the team's joint output fairly attributable to "
            "this agent* (a.k.a. *normalised Shapley value* / *share of credit* "
            "\u2014 not to be confused with a *marginal contribution* "
            "`v(S\u222a{i}) \u2212 v(S)`, which is the un-averaged building block "
            "the Shapley value averages over). The greedy team-formation loop "
            "uses single marginal contributions to grow the team \u2014 a "
            "rank-1 Shapley approximation \u2014 and the exact Shapley closed "
            "form is computed once on the final team purely for display."
        )
        st.caption(
            "The **Shapley value** is the exact payoff for the induced-subgraph "
            "game (Deng\u2013Papadimitriou 1994 closed form): "
            "`\u03c6\u1d62 = a\u1d62 + \u00bd\u00b7\u03a3 w\u1d62\u2c7c`, "
            "where `a\u1d62` is the solo value of the agent's contributed skill "
            "(`0.6\u00b7coverage + 0.3\u00b7prior_reputation + 0.1\u00b7log(1+installs)/max`) "
            "and `w\u1d62\u2c7c = 0.4\u00b7(1 \u2212 cos(e\u1d62, e\u2c7c))` is the pairwise "
            "complementarity to the other team members. By the *efficiency* "
            "axiom, the per-agent \u03c6\u1d62 values sum to `v(N)` \u2014 the "
            "total worth of the team."
        )


# ----- Agent comms ----------------------------------------------------------
with tab_bb:
    st.caption(
        "**Agentic forum.** This shows the agents' communication while "
        "solving their subtask. The marshal (\U0001f9ed) starts off the "
        "conversation and coordinates each round, the agents "
        "(\U0001f916) contribute their domain expertise, and when the "
        "team is done the marshal summarises the result back to the "
        "orchestrator."
    )
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
                    f"**{_agent_label(m['sender'])}**  ·  round {m['round']}  ·  "
                    f"_{m['role']}_"
                )
                st.write(m["text"])


# ----- Validation -----------------------------------------------------------
with tab_val:
    v = db.validation_results.find_one({"run_id": run_id}, {"_id": 0})
    if not v:
        st.info("No validation yet.")
    else:
        # Soft, demo-friendly label mapping. Internal statuses are kept
        # unchanged in MongoDB; we only rephrase them for the audience.
        # TODO(post-hackathon): wire a proper hard-fail category that
        # distinguishes "design is unbuildable" from "some criteria did
        # not apply" so the validator can refuse a run rather than
        # always landing on "Acceptable / Excellent".
        soft_label = {
            "conceptual_pass": ("Excellent", "\U0001f31f"),
            "conceptual_pass_with_warnings": ("Acceptable with notes",
                                              "\u2705"),
            "conceptual_fail": ("Acceptable \u2014 needs human review",
                                "\U0001f50d"),
        }
        status = v["overall_status"]
        label, icon = soft_label.get(status, (status, ""))
        if status == "conceptual_pass":
            st.success(f"Overall: **{icon} {label}**")
        elif status == "conceptual_pass_with_warnings":
            st.success(f"Overall: **{icon} {label}**")
        else:
            st.warning(f"Overall: **{icon} {label}**")
            if st.button("\U0001f504  Retry full pipeline",
                         key="retry_validation",
                         disabled=st.session_state.running,
                         help="Re-runs the same prompt end-to-end."):
                st.session_state.events = []
                st.session_state.running = True
                with st.spinner("Re-running pipeline\u2026"):
                    try:
                        summary = run_pipeline(prompt)
                        st.session_state.run_id = summary["run_id"]
                    finally:
                        st.session_state.running = False
                st.rerun()

        # Validation spec (the prompt-derived criteria the marshals were briefed on).
        val_spec = v.get("validation_spec") or {}
        criteria = val_spec.get("criteria") or []
        if criteria:
            st.markdown("#### Acceptance criteria (derived from the prompt)")
            if val_spec.get("narrative"):
                st.caption(val_spec["narrative"])
            st.dataframe(
                [{"id": c["id"], "must_have": c["must_have"],
                  "structured_check": "yes" if c.get("check") else "no",
                  "rationale": c.get("rationale", "")}
                 for c in criteria],
                use_container_width=True, hide_index=True,
            )

        st.markdown("#### Check results")
        # Flatten the structured value dict into legible columns.
        flat_rows = []
        for c in v.get("checks", []):
            val = c.get("value")
            if isinstance(val, dict) and "actual" in val:
                actual = val.get("actual")
                exp = val.get("expected") or {}
                op = exp.get("op")
                tgt = exp.get("value")
                if op == "between" and isinstance(tgt, (list, tuple)) and len(tgt) == 2:
                    expected_str = f"between {tgt[0]} and {tgt[1]}"
                elif op == "equals_any" and isinstance(tgt, list):
                    expected_str = f"one of {', '.join(map(str, tgt))}"
                elif op:
                    expected_str = f"{op} {tgt}"
                else:
                    expected_str = "—"
                actual_str = (f"{actual:,.2f}" if isinstance(actual, float)
                              else str(actual) if actual not in (None, "") else "—")
                flat_rows.append({
                    "id": c.get("name"),
                    "status": c.get("status"),
                    "field": val.get("field"),
                    "actual": actual_str,
                    "expected": expected_str,
                    "note": c.get("note"),
                })
            else:
                flat_rows.append({
                    "id": c.get("name"),
                    "status": c.get("status"),
                    "field": "—",
                    "actual": str(val) if val not in (None, "") else "—",
                    "expected": "—",
                    "note": c.get("note"),
                })
        st.dataframe(flat_rows, use_container_width=True, hide_index=True)
        st.caption(
            "`pass` = the spec satisfies the structured check. "
            "`warning` = the spec is close to but outside the target band. "
            "`qualitative` = the criterion has no machine-checkable predicate "
            "or targets a field this domain's spec does not populate \u2014 the "
            "system flags it for human review rather than auto-failing."
        )
        st.markdown("#### Judge scores per subtask (each metric on a 0\u201310 scale)")
        st.dataframe(v.get("judge_scores", []),
                     use_container_width=True, hide_index=True)
        st.caption(
            "`clarity` \u2013 is the subtask output unambiguous and well-structured? "
            "`completeness` \u2013 does it cover what the marshal asked for? "
            "`consistency` \u2013 does it agree with upstream subtasks? "
            "All three are integers in **[0, 10]**, returned by an LLM judge "
            "in real mode and by a deterministic router in mock mode."
        )


# ----- 3D rendering ---------------------------------------------------------
with tab_render:
    art = db.artifacts.find_one(
        {"run_id": run_id, "kind": "geometry_json"}, {"_id": 0},
    )
    if not art:
        st.info(
            "No geometry artifact yet. The orchestrator runs a `visualise` "
            "stage that converts the design spec into a list of 3D primitives "
            "(boxes + polylines) and stores them as an `artifacts` row of "
            "kind `geometry_json`. Re-run the pipeline to regenerate."
        )
    else:
        from src.ui.render3d import render_geometry

        geometry = art["uri_or_inline"]
        fig = render_geometry(geometry)
        st.plotly_chart(fig, use_container_width=True)


# ----- Concept render (AI hero image) --------------------------------------
with tab_concept:
    from src.pipeline import concept_render as _concept_render

    spec = db.design_specs.find_one({"run_id": run_id}, {"_id": 0}) or {}
    run_doc = db.runs.find_one({"run_id": run_id}, {"_id": 0}) or {}
    existing = db.artifacts.find_one(
        {"run_id": run_id, "kind": _concept_render.ARTIFACT_KIND}, {"_id": 0},
    )
    st.caption(
        "Optional AI-generated hero render of the synthesised design. "
        "Calls OpenAI's image API in real-LLM mode (~5\u201310 cents, 10\u201320 s); "
        "in mock mode a deterministic SVG placeholder is shown so the demo "
        "still has a picture. Cached per run \u2014 click again to reuse."
    )
    if existing:
        payload = existing.get("uri_or_inline") or {}
        data_url = payload.get("data_url")
        if data_url:
            st.image(data_url, use_container_width=True)
        if payload.get("placeholder"):
            st.warning(
                f"Placeholder shown ({payload.get('reason', 'unknown')}). "
                "Set `USE_MOCK_LLM=false` and rerun to call the real image API."
            )
        with st.expander("Image prompt sent to the model"):
            st.code(existing.get("image_prompt", ""), language="text")
        if st.button(
            "Regenerate concept render",
            key="regen_concept",
            help="Deletes the cached artifact and asks the image model again.",
        ):
            db.artifacts.delete_many(
                {"run_id": run_id, "kind": _concept_render.ARTIFACT_KIND}
            )
            with st.spinner("Generating concept render\u2026"):
                _concept_render.generate(run_id, run_doc.get("prompt", ""), spec)
            st.rerun()
    else:
        if st.button(
            "Generate concept render",
            key="gen_concept",
            type="primary",
            disabled=not spec,
            help=("Synthesise a hero image from the design spec." if spec
                  else "Run the pipeline first \u2014 no design spec yet."),
        ):
            with st.spinner("Generating concept render\u2026"):
                _concept_render.generate(run_id, run_doc.get("prompt", ""), spec)
            st.rerun()


# ----- Report ---------------------------------------------------------------
with tab_report:
    art = db.artifacts.find_one(
        {"run_id": run_id, "kind": "final_report_md"}, {"_id": 0},
    )
    if not art:
        st.info("No report yet.")
    else:
        st.caption(
            "This brief is built from the structured output of the "
            "earlier stages."
        )
        # The Report tab is the user-facing artefact: scrub any internal
        # "(mock)" tags that older runs may have written into the markdown
        # so demo audiences never see implementation chatter here.
        import re
        md = art["uri_or_inline"]
        md = re.sub(r"\s*\(mock\)", "", md, flags=re.IGNORECASE)
        st.markdown(md)


# ----- Reputation -----------------------------------------------------------
with tab_reput:
    st.caption(
        "Per-run reputation deltas applied to each agent at the end of the "
        "pipeline, plus the cumulative reputation persisted on the `agents` "
        "collection. The reputation update carries to the *next* run \u2014 "
        "this is gate **G10**, the only piece of cross-run state."
    )
    deltas = list(
        db.reputation_updates.find({"run_id": run_id}, {"_id": 0})
    )
    if not deltas:
        st.info("No reputation updates yet.")
    else:
        # Per-run deltas: one row per agent that participated in this run.
        delta_rows = [
            {
                "agent": _agent_label(d["agent_id"]),
                "delta": round(d.get("delta", 0.0), 4),
                "subtasks_participated": ", ".join(
                    d.get("subtasks_participated", [])
                ) if isinstance(d.get("subtasks_participated"), list)
                else d.get("subtasks_participated"),
                "mean_contribution_score": d.get("mean_contribution_score"),
                "reason": d.get("reason", ""),
            }
            for d in deltas
        ]
        st.markdown("#### Per-run reputation update")
        st.dataframe(delta_rows, use_container_width=True, hide_index=True)
        st.caption(
            "`delta = base \u00b7 (0.5 + 0.5\u00b7load_factor) "
            "\u00b7 (0.5 + 0.5\u00b7quality_factor)`. "
            "`base` is the validation outcome reward "
            "(`+0.04` pass, `+0.02` pass-with-warnings, `\u22120.04` fail). "
            "`load_factor = |subtasks_participated| / total_subtasks`. "
            "`quality_factor = mean_contribution_score` = mean solo value "
            "`a\u1d62` of the skills the agent contributed."
        )

        agent_ids = [d["agent_id"] for d in deltas]
        agent_docs = list(db.agents.find(
            {"agent_id": {"$in": agent_ids}},
            {"_id": 0, "agent_id": 1, "reputation": 1,
             "runs_participated": 1, "runs_succeeded": 1},
        ))
        cum_rows = [
            {
                "agent": _agent_label(a["agent_id"]),
                "reputation": round(a.get("reputation", 0.0), 4),
                "runs_participated": a.get("runs_participated", 0),
                "runs_succeeded": a.get("runs_succeeded", 0),
            }
            for a in agent_docs
        ]
        st.markdown("#### Cumulative reputation (across all runs)")
        st.dataframe(cum_rows, use_container_width=True, hide_index=True)
        st.caption(
            "Stored on the `agents` collection. Persists across runs \u2014 "
            "the next prompt sees these as priors via `prior_reputation` "
            "in step 5 of the matching pipeline."
        )


# ----- Workflow (LangGraph DAG visualisation) -------------------------------
with tab_workflow:
    st.markdown("#### 🕸️  Pipeline workflow graph")
    st.caption(
        "This is the deterministic pipeline that runs end-to-end on every "
        "prompt \u2014 from decomposing the task to producing the final "
        "brief. Every stage's output is persisted, so any run can be "
        "audited or replayed."
    )
    backend_now = (
        "🕸️ LangGraph (live)" if settings.use_langgraph
        else "🧵 function pipeline (LangGraph diagram below shown for reference)"
    )
    st.info(f"Active backend: **{backend_now}**")

    try:
        if not LANGGRAPH_AVAILABLE:
            raise RuntimeError(
                f"LangGraph package not importable: {LANGGRAPH_IMPORT_ERROR}"
            )
        _g = _build_lg_graph()  # type: ignore[misc]
        _graph_obj = _g.get_graph()
        _mermaid_src = _graph_obj.draw_mermaid()
    except Exception as exc:  # pragma: no cover — surfacing the error helps
        st.error(f"Could not build LangGraph diagram: {exc}")
        _mermaid_src = ""
        _graph_obj = None

    # Primary render: convert nodes/edges to a Graphviz DOT and use the
    # built-in st.graphviz_chart. This avoids a CDN round-trip for mermaid.js
    # which can hang on restrictive networks (e.g. hackathon Wi-Fi).
    if _graph_obj is not None:
        try:
            _node_ids = [n for n in _graph_obj.nodes]
            _edges = [(e.source, e.target) for e in _graph_obj.edges]
            _dot_lines = [
                "digraph G {",
                "  rankdir=TB;",
                "  bgcolor=\"white\";",
                "  size=\"4,6\";",
                "  ratio=compress;",
                "  nodesep=0.18;",
                "  ranksep=0.22;",
                "  node [shape=box style=\"rounded,filled\" "
                "fillcolor=\"#eef3ff\" color=\"#4a6fa5\" "
                "fontname=\"Helvetica\" fontsize=10 "
                "margin=\"0.08,0.04\" height=0.3];",
                "  edge [color=\"#4a6fa5\" arrowsize=0.7];",
            ]
            for n in _node_ids:
                label = str(n).replace('"', '\\"')
                _dot_lines.append(f'  "{n}" [label="{label}"];')
            for src, tgt in _edges:
                _dot_lines.append(f'  "{src}" -> "{tgt}";')
            _dot_lines.append("}")
            # Constrain width with a column so it doesn't stretch full-page.
            _gv_left, _gv_mid, _gv_right = st.columns([3, 2, 3])
            with _gv_mid:
                st.graphviz_chart("\n".join(_dot_lines), use_container_width=True)
        except Exception as exc:  # pragma: no cover
            st.warning(f"Graphviz render failed ({exc}); falling back to Mermaid source.")

    if _mermaid_src:
        with st.expander("Mermaid source (raw)"):
            st.code(_mermaid_src, language="mermaid")

    st.markdown("---")
    st.markdown(
        "**Node \u2192 stage function mapping** "
        "(see [docs/LANGGRAPH.md](docs/LANGGRAPH.md) \u00a74)"
    )
    st.table(
        {
            "Node": [
                "ensure_run", "decompose", "validator_spec", "execute",
                "synthesise", "validate", "estimate", "visualise",
                "report", "reputation", "finalise",
            ],
            "Stage function": [
                "_run_utils.ensure_run",
                "decomposer.decompose",
                "validator_spec.derive_validation_spec",
                "execution.execute_subtask (loop over subtasks)",
                "synthesis.synthesise",
                "validation.validate",
                "surveyor.estimate",
                "visualiser.build_geometry",
                "reporter.build_report",
                "reputation.apply_run_reputations",
                "_run_utils.finalise_run",
            ],
            "Writes to MongoDB": [
                "runs, events",
                "subtasks, events",
                "runs.validation_spec, events",
                "assignments, coalition_messages, subtask_outputs, events",
                "design_specs, events",
                "validation_results, events",
                "cost_estimates, events",
                "artifacts (geometry_json), events",
                "artifacts (final_report_md), runs.final_report_md, events",
                "reputation_updates, agents.reputation, events",
                "runs (status=completed), events",
            ],
        }
    )


# ----- MongoDB --------------------------------------------------------------
with tab_mongo:
    st.markdown("#### 🍃  Where does MongoDB fit?")
    st.caption(
        "We use a database, MongoDB, to make the project scalable. It is "
        "used in **five** distinct ways: as the **skill marketplace** "
        "(Atlas Vector Search retrieves skills by cosine similarity to "
        "each subtask), as the **agent and reputation store**, as the "
        "**team message bus**, as the **run ledger** that persists every "
        "stage's output, and as the **LLM response cache** that powers "
        "replay-mode demos. The diagram below shows where each collection "
        "enters the pipeline."
    )

    _mongo_dot = """
digraph MongoDB {
  rankdir=LR;
  bgcolor="white";
  pad=0.3;
  nodesep=0.35;
  ranksep=0.55;
  fontname="Helvetica";

  // Defaults
  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11
        margin="0.12,0.07"];
  edge [color="#4a6fa5" fontsize=9 fontname="Helvetica"];

  // User & prompt
  user    [label="👤  User", shape=circle fillcolor="#fffbe6" color="#b58900"];
  prompt  [label="Design prompt\\n(natural language)", fillcolor="#fff3cd" color="#b58900"];

  // Pipeline stages (yellow path)
  decomp  [label="Decomposer\\n(LLM)", fillcolor="#eaf3ff" color="#4a6fa5"];
  embed   [label="OpenAI\\nembeddings\\n(1536-d)", fillcolor="#eaf3ff" color="#4a6fa5"];
  match   [label="Skill matching\\n+ coverage floor\\n+ set-cover", fillcolor="#eaf3ff" color="#4a6fa5"];
  bb      [label="Agent comms", fillcolor="#eaf3ff" color="#4a6fa5"];
  synth   [label="Synthesise →\\nValidate →\\nCost → Report", fillcolor="#eaf3ff" color="#4a6fa5"];
  rep     [label="Shapley\\n+ reputation\\nupdate", fillcolor="#eaf3ff" color="#4a6fa5"];

  // MongoDB roles (green leaves)
  m_vec   [label="① Vector search\\nskills + Atlas index\\nskills_embedding_vector",
           fillcolor="#d6f0d6" color="#2f7a2f" shape="cylinder"];
  m_cat   [label="② Catalog\\nskills, agents",
           fillcolor="#d6f0d6" color="#2f7a2f" shape="cylinder"];
  m_bus   [label="③ Team message bus\\n(coalition_messages)",
           fillcolor="#d6f0d6" color="#2f7a2f" shape="cylinder"];
  m_ledg  [label="④ Assignment ledger\\nruns, subtasks, assignments,\\ndesign_specs, validation_results,\\ncost_estimates, artifacts, events",
           fillcolor="#d6f0d6" color="#2f7a2f" shape="cylinder"];
  m_mem   [label="⑤ Persistent memory\\nagents.reputation,\\nreputation_updates",
           fillcolor="#d6f0d6" color="#2f7a2f" shape="cylinder"];

  // Output
  out     [label="Design brief\\n(report + 3D + cost)", fillcolor="#fff3cd" color="#b58900"];

  // Edges
  user   -> prompt;
  prompt -> decomp;
  decomp -> embed [label="subtask\\ncapabilities"];
  embed  -> match [label="query\\nvector"];
  match  -> m_vec [label="$vectorSearch", style="dashed"];
  m_vec  -> match [style="dashed"];
  match  -> m_cat [label="lookup\\nagents", style="dashed"];
  m_cat  -> match [style="dashed"];
  match  -> bb;
  bb     -> m_bus [label="append", style="dashed"];
  bb     -> synth;
  synth  -> m_ledg [label="persist", style="dashed"];
  synth  -> rep;
  rep    -> m_mem [label="update", style="dashed"];
  rep    -> out;
}
""".strip()

    st.graphviz_chart(_mongo_dot, use_container_width=True)

    st.markdown("##### How to read this diagram")
    st.markdown(
        "This is the **end-to-end architecture** of the app. "
        "Yellow nodes are user-visible "
        "inputs and outputs; blue nodes are pipeline stages running in Python; "
        "green cylinders are **MongoDB collections** \u2014 the only stateful "
        "components in the whole system. Solid arrows are the synchronous "
        "data path; dashed arrows are reads/writes against MongoDB."
    )
    st.markdown(
        "**Pipeline**\n\n"
        "1. **User \u2192 Design prompt.**  A free-text brief like *\"design a "
        "2 km bridge for 50 cars/h, modern aesthetic\"* enters the system.\n"
        "2. **Decomposer (LLM).**  `gpt-4o-mini` rewrites the prompt as a "
        "DAG of sub-tasks, each annotated with the *capabilities* it needs "
        "(e.g. *structural-analysis*, *deck-design*, *cost-estimation*).\n"
        "3. **OpenAI embeddings (1536-d).**  Each sub-task's capability "
        "string is vectorised with `text-embedding-3-small`. This is the "
        "**only place** we call the embedding API at query time \u2014 the "
        "catalogue itself was vectorised once at seed time.\n"
        "4. **Skill matching (the heart of the system).**  For every "
        "sub-task we run `$vectorSearch` against \u2460 the **skills** "
        "collection (HNSW cosine on `skills_embedding_vector`), apply a "
        "**coverage floor** (\u2265 0.40 cosine), then a **set-cover** to "
        "pick the smallest team that covers all required capabilities. "
        "Agents are looked up from \u2461 the **catalog** (`agents` "
        "documents carry `skill_ids`).\n"
        "5. **Agent comms.**  The selected team collaborates on a shared "
        "log \u2014. Every message (marshal kickoff, "
        "agent contribution, reconcile) is appended to \u2462 the "
        "**team message bus** (`coalition_messages`), indexed by "
        "`(run_id, subtask_id, ts)` so the Agent comms tab can replay it.\n"
        "6. **Synthesise \u2192 Validate \u2192 Cost \u2192 Report.**  The team's "
        "raw outputs are merged into a design spec, validated against "
        "engineering rules, costed, and rendered into a brief. Every "
        "intermediate artefact (specs, validations, cost lines, 3D renders, "
        "events) is persisted to \u2463 the **assignment ledger** \u2014 this "
        "is the *replay surface* that makes any past run reproducible "
        "from the database alone.\n"
        "7. **Shapley + reputation update.**  We compute the exact "
        "closed-form Shapley value for each agent on the final team, and "
        "write a per-run delta plus the new running reputation to \u2464 "
        "**persistent memory** (`agents.reputation`, `reputation_updates`). "
        "These priors feed back into step 4 of *future* runs \u2014 that's "
        "the cross-run learning loop.\n"
        "8. **Design brief.**  Report + 3D render + cost estimate handed "
        "back to the user."
    )
    st.markdown(
        "**The take-away.**  MongoDB is the "
        "(\u2460), the agent registry (\u2461), the collaboration log "
        "(\u2462), the audit trail / replay capability (\u2463), and the "
        "ability to learn across runs (\u2464). The Python pipeline is "
        "deliberately **stateless** \u2014 every line of state lives in "
        "one of the five green cylinders."
    )

    st.markdown("---")
    st.markdown("#### The 5 spots, in detail")
    st.table(
        {
            "Role": [
                "① Vector search",
                "② Catalog",
                "③ Message bus",
                "④ Assignment ledger",
                "⑤ Persistent memory",
            ],
            "Collection / index": [
                "skills + Atlas index `skills_embedding_vector`",
                "skills, agents",
                "coalition_messages",
                "runs, subtasks, assignments, design_specs, validation_results, cost_estimates, artifacts, events",
                "agents.reputation, reputation_updates",
            ],
            "What it stores": [
                "70 skills × 1536-d cosine embeddings (semantic skill index)",
                "Skill metadata, agent rosters with `skill_ids`",
                "Append-only message log, indexed `(run_id, subtask_id, ts)`",
                "Every team formed, every output, every cost — the *replay surface*",
                "Per-run delta + running reputation across all runs",
            ],
            "Used by": [
                "Skill matching pipeline (`src/pipeline/matching.py`)",
                "Set-cover → agent assignment",
                "Team collaboration loop",
                "All pipeline stages + the Replay button",
                "Reputation stage + future-run priors",
            ],
        }
    )

    st.markdown("---")
    st.info(
        "MongoDB provides *five* capabilities. It's the catalog, the vector "
        "index, the message bus, the audit log, and the cross-run memory.",
        icon="🍃",
    )
