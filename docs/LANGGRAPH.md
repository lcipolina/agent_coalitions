# LangGraph orchestrator (parallel implementation)

> Branch: `langgraph`. Opt-in via the `USE_LANGGRAPH=true` env var. The
> default code path on `master` is unchanged.

## 1. What is LangGraph (and what it is not)

**LangGraph** is a small Python library for building **stateful, directed
graphs of functions** — typically LLM agents and tool calls — where each
node updates a shared `state` object and edges decide what runs next.

It is built by the LangChain team but is a **separate package** from
LangChain. The two are easy to confuse:

| | LangChain | LangGraph |
| --- | --- | --- |
| Purpose | LLM/tool **abstractions** (prompts, chat models, retrievers, tool calling, output parsers). | **Workflow engine** for multi-step / multi-agent pipelines. State graph of typed nodes + edges. |
| Unit of composition | `Runnable` chain (linear). | `StateGraph` node (DAG, with conditional branches and loops). |
| Persistence | none built-in | optional `Checkpointer` (SQLite, Postgres, in-memory). |
| Used here | **No.** Our LLM client `src/llm/openai_client.py` is plain `openai.OpenAI(...)`; we do not use LangChain `Runnable` chains. | **Yes** — for the pipeline orchestrator only. |

So: this branch adds **only** LangGraph, **not** LangChain. We keep our
direct `openai` calls and our hand-written prompt templates.

## 2. Why we picked it (now, not on day 1)

The hackathon brief explicitly named LangGraph in §6 ("LangGraph for
workflow orchestration"). The 1-day MVP shipped with a plain function
pipeline (`src/pipeline/orchestrator.py`) because LangGraph adds API
overhead that wasn't worth paying under demo-day time pressure. With the
demo working, the cost of porting is low and we get four concrete
benefits:

1. **Visualisable workflow.** The graph object can render itself
   (`graph.get_graph().draw_mermaid()`) — a free architecture diagram for
   slides and the report.
2. **Conditional edges.** Today the pipeline is a strict linear chain;
   if we ever want "skip cost estimate when validation fails" or "loop
   back to synthesis if a critic rejects the spec", LangGraph expresses
   it cleanly with `add_conditional_edges`. Today we'd hand-code branch
   logic in `run_pipeline`.
3. **Standard vocabulary.** Reviewers, future engineers, and other LLM
   coding agents recognise `StateGraph`, `add_node`, `add_edge`. The
   private function pipeline is undocumented to anyone outside the repo.
4. **Pause / resume / replay alignment.** LangGraph's `Checkpointer`
   abstraction matches what we already do with MongoDB's `runs` and
   `events` rows. The migration is a natural place to clean up the
   replay path long-term — though we **do not** turn on the checkpointer
   in this PR (see §5.5).

## 3. What it gives us (concretely)

For our 9-stage pipeline (decompose → execute → synthesise → validate →
cost → visualise → report → reputation), LangGraph gives us:

- **`StateGraph(GraphState)`** — a typed container for the whole run.
  Each node returns a *partial* state dict and LangGraph merges it.
  No more passing `(run_id, prompt, spec, validation, cost)` through
  positional arguments.
- **`add_node(name, fn)` + `add_edge(a, b)`** — declarative wiring. The
  pipeline shape is one block of code, separate from the stage logic.
- **`compile()`** — produces a runnable graph with `.invoke(input_state)`,
  `.stream(...)` (for live progress), and `.get_graph()` (for diagrams).
- **No new dependencies for our use case.** `langgraph` is already in
  `requirements.txt`. We don't pull in LangChain at all.

What it does **not** give us, and we explicitly do not use:

- We **don't** use `ToolNode` — our LLM client wraps tool calls itself.
- We **don't** use `MessagesState` / chat-message state — our state is
  domain artifacts (spec, validation, cost), not chat history.
- We **don't** use `Send` / `Map` parallelism for the subtask loop in
  this PR — preserves the existing topological-order semantics.
- We **don't** turn on a `Checkpointer` in this PR — MongoDB already
  persists every artifact and event.

## 4. How we are using it

Side-by-side with the existing function pipeline. The user picks the
backend at runtime via an env var:

```
USE_LANGGRAPH=false   # default — runs src/pipeline/orchestrator.py
USE_LANGGRAPH=true    # runs src/pipeline/orchestrator_lg.py
```

Both produce **byte-identical MongoDB rows** because the LangGraph nodes
are thin wrappers that call the **exact same stage functions**. The
graph engine is the orchestrator only; it is not aware of any business
logic, prompts, or DB writes.

### 4.1 The graph

```
                 ┌─────────────┐
                 │ ensure_run  │
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │  decompose  │
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │ validator_  │
                 │   spec      │
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │  execute    │   (loop over ordered subtasks)
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │ synthesise  │
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │  validate   │
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │    cost     │
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │  visualise  │
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │   report    │
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │ reputation  │
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │  finalise   │
                 └──────┬──────┘
                        ▼
                       END
```

Linear today, intentionally. Conditional branches (e.g. "skip cost on
validation fail") are easy to add later with `add_conditional_edges`.

### 4.2 The state

```python
class GraphState(TypedDict, total=False):
    run_id: str
    prompt: str
    subtasks: list[dict]      # set by decompose_node
    criteria: list[dict]      # set by validator_spec_node
    spec: dict                # set by synthesise_node
    validation: dict
    cost: dict
    report_md: str
    n_reputation_updates: int
```

Each node returns a partial dict; LangGraph merges. Nothing exotic.

### 4.3 Live-progress hooks

The Streamlit live-progress pane (`app.py`) listens to `emit(...)` calls
from `src.core.progress`. To preserve that, every LangGraph node is
wrapped in a tiny decorator `_with_emit("stage_name")` that emits
`stage_start` / `stage_end` around the underlying stage function. The
decorator is the **only** thing nodes do beyond calling the existing
stage function and packaging its return value into a partial state.

## 5. How it is integrated

### 5.1 Files added on this branch

- `docs/LANGGRAPH.md` — this document.
- `src/pipeline/_run_utils.py` — extracted helpers (`_ensure_run`,
  `_topo_order`, `_upstream_outputs`, `_now`, `_finalise_run`) shared
  between both orchestrators.
- `src/pipeline/orchestrator_lg.py` — the LangGraph backend. Exposes
  `run_pipeline(prompt) -> dict` with the same signature and return
  shape as the function backend.
- `tests/test_orchestrator_lg.py` — the same end-to-end smoke test as
  for the function backend, asserted against the LangGraph backend.

### 5.2 Files modified on this branch

- `src/core/config.py` — adds `use_langgraph: bool = False` (env var
  `USE_LANGGRAPH`).
- `src/pipeline/orchestrator.py` — the private helpers move into
  `_run_utils.py`; the file imports them back. No behaviour change.
- `app.py` — picks the backend at import time based on
  `settings.use_langgraph`. The replay path is unchanged (always
  function backend).

### 5.3 What is preserved

- All existing tests pass (14/14 with the two new LangGraph tests).
- The mock-mode demo works without an OpenAI key.
- MongoDB row shape identical (assignments, coalition_messages,
  subtask_outputs, design_specs, validation_results, cost_estimates,
  artifacts, reputation_updates, events).
- The Streamlit live-progress pane works against both backends because
  both call the same `emit(...)` hooks.
- Replay (`G9` invariant: zero LLM calls on replay) is unchanged. It
  stays in the function backend; LangGraph is only for live runs.

### 5.4 Visible in the demo UI

LangGraph is not just behind the curtain — the Streamlit app surfaces
it in three places so demo audiences can see the integration:

1. **Sidebar toggle.** A *LangGraph backend* switch (next to the
   *Mock LLM* toggle) flips `settings.use_langgraph` for the live
   session. No restart needed; the next *Run pipeline* click goes
   through the chosen backend. Disabled while a run is in flight.
2. **Status badge.** Right under the toggle a coloured pill shows
   either `🕸️ Pipeline: LangGraph (StateGraph)` or
   `🧵 Pipeline: function (plain Python)`. The same label is repeated
   under the page title so it stays in view when the sidebar is
   collapsed.
3. **🕸️ Workflow tab.** A new tab renders the compiled graph as a
   Mermaid diagram (via `graph.get_graph().draw_mermaid()` + mermaid.js
   from CDN). Below the diagram, a table maps each node to the stage
   function it wraps and the MongoDB collections it writes to. The
   tab is available regardless of which backend is active — when the
   function backend is selected the diagram still shows the canonical
   structure both backends share.

In other words: when you flip the sidebar toggle and run the pipeline,
the badge changes, the *Workflow* tab confirms the active backend, and
every other tab works exactly as before because the LangGraph nodes
call the same stage functions.

### 5.5 What is deliberately out of scope (future work)

- `Checkpointer` (SQLite/Postgres). MongoDB already persists every
  artifact; adding a second store is redundant and a foot-gun.
- `Send` / `Map` parallelism for the subtask loop. The current sequential
  loop respects `_topo_order` dependency edges; parallelising correctly
  is a separate ticket.
- Conditional edges (e.g. skip cost on validation fail). Easy to add
  later — the value of this PR is *getting onto LangGraph*, not adding
  new behaviour.
- Migrating to LangGraph's `MessagesState` for the blackboard
  collaboration inside `execute_subtask`. The blackboard already
  persists every message to `coalition_messages`; LangGraph state would
  be a third copy.

## 6. How to use it

```bash
# default behaviour, function pipeline
streamlit run app.py

# LangGraph backend
USE_LANGGRAPH=true streamlit run app.py

# CLI smoke test (function backend)
conda run -n coalitions python -m src.run

# CLI smoke test (LangGraph backend)
USE_LANGGRAPH=true conda run -n coalitions python -m src.run

# tests — both backends
conda run -n coalitions pytest tests/ -q
```

You can also flip the backend **at runtime** from the Streamlit
sidebar (toggle: *LangGraph backend*) without restarting. The
*🕸️ Workflow* tab renders the compiled graph as a Mermaid diagram +
node-to-stage mapping table, so the LangGraph integration is visible
even before you trigger a run.

## 7. References

- LangGraph docs: https://langchain-ai.github.io/langgraph/
- StateGraph API: https://langchain-ai.github.io/langgraph/reference/graphs/
- The function backend this mirrors: [src/pipeline/orchestrator.py](../src/pipeline/orchestrator.py)
