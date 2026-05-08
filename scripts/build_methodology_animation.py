"""Build the animated methodology diagram for social posts.

Produces two files in ``docs/social/``:
    VID-2-methodology.gif   (~7 s, looping)
    VID-2-methodology.mp4   (~7 s, looping)

Run:
    conda run -n coalitions --no-capture-output \\
        python scripts/build_methodology_animation.py

Two-phase animation:
    Phase 1 (forward build, frames 0..N-3):
        Pieces appear left-to-right, top-to-bottom -- prompt, orchestrator,
        subtask chips, marketplace cylinder, mechanism strip, three teams
        (marshal then agents), in-team A2A arrows.

    Phase 2 (backward pulse, frames N-2..N-1):
        Agents -> Marshal -> Orchestrator arrows recolored amber to
        signal "results flow back up", and the final design brief node
        appears at the bottom.

The full diagram is then held for ~1 s before the GIF/MP4 loops.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import imageio.v2 as imageio
from PIL import Image

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "social"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Per-frame state. Each frame is a *delta* applied to a cumulative state.
# We accumulate by toggling booleans; the renderer walks the booleans and
# emits matching DOT.
# ---------------------------------------------------------------------------

# Color palette (matches the live Streamlit Methodology tab).
COL_USER     = ("#fff3cd", "#b58900")
COL_ORCH     = ("#eaf3ff", "#4a6fa5")
COL_T1       = ("#e6f0ff", "#4a6fa5")
COL_T2       = ("#fde6f0", "#a64a7a")
COL_T3       = ("#e6f7e6", "#2f7a2f")
COL_MKT_CYL  = ("#d6f0d6", "#2f7a2f")
COL_MKT_BOX  = ("#eaf7ea", "#2f7a2f")
COL_BRIEF    = ("#fff3cd", "#b58900")
EDGE_BLUE    = "#4a6fa5"
PULSE_AMBER  = "#e89b1f"

TEAM_COLORS = {
    "T1": ("#dbe8ff", "#4a6fa5", "#9ab4d8", "#f4f8ff"),  # marshal_fill, marshal_edge, a2a_color, cluster_fill
    "T2": ("#ffd9e8", "#a64a7a", "#d8a0bc", "#fff4f8"),
    "T3": ("#cfe9cf", "#2f7a2f", "#9ad89a", "#f4fff4"),
}

TEAM_LABELS = {"T1": "structural", "T2": "design", "T3": "cost"}

TEAM_AGENTS = {
    "T1": [("a1a", "load-calc"), ("a1b", "FEA"), ("a1c", "CAD")],
    "T2": [("a2a", "form"), ("a2b", "material"), ("a2c", "color")],
    "T3": [("a3a", "BOM"), ("a3b", "risk"), ("a3c", "plan")],
}


def _team_cluster(
    name: str,
    state: dict,
    fillcolor: str,
    border: str,
    a2a_color: str,
    cluster_fill: str,
    pulse_marshal_to_orch: bool,
    pulse_agents_to_marshal: bool,
) -> str:
    """Return DOT for one team's cluster, respecting visibility flags."""
    label = TEAM_LABELS[name]
    marshal_id = f"m{name[1]}"
    agents = TEAM_AGENTS[name]

    lines = [
        f'subgraph cluster_{name} {{',
        '  label=""; style="rounded,filled";',
        f'  fillcolor="{cluster_fill}"; color="{border}";',
    ]
    if state.get(f"marshal_{name}"):
        lines.append(
            f'  {marshal_id} [label="Marshal {name}\n“{label}”", '
            f'fillcolor="{fillcolor}" color="{border}" fontname="Helvetica-Bold"];'
        )
    for aid, skill in agents:
        if state.get(f"agent_{aid}"):
            lines.append(
                f'  {aid} [label="agent\n{skill}" '
                f'fillcolor="#ffffff" color="{border}" fontsize=10];'
            )
    # Marshal -> agent edges (with pulse on backward phase).
    edge_color = PULSE_AMBER if pulse_agents_to_marshal else border
    edge_attrs = f' [color="{edge_color}" penwidth={3 if pulse_agents_to_marshal else 1}]'
    if pulse_agents_to_marshal:
        edge_attrs = f' [color="{edge_color}" penwidth=3 dir=back]'
    for aid, _ in agents:
        if state.get(f"agent_{aid}") and state.get(f"marshal_{name}"):
            lines.append(f'  {marshal_id} -> {aid}{edge_attrs};')
    # In-team A2A arrows between adjacent agents.
    if state.get(f"a2a_{name}"):
        a, b, c = (aid for aid, _ in agents)
        lines.append(
            f'  {a} -> {b} [dir=both color="{a2a_color}" '
            f'label="A2A" fontsize=8];'
        )
        lines.append(
            f'  {b} -> {c} [dir=both color="{a2a_color}" '
            f'label="A2A" fontsize=8];'
        )
    lines.append('}')
    return "\n".join(lines)


def render_dot(state: dict) -> str:
    """Render the cumulative state as a single DOT graph."""
    # Optional banner at the top — used during prompt-swap phase.
    banner = state.get("banner")
    label_attr = (
        f'  label=<<FONT POINT-SIZE="22"><B>{banner}</B></FONT>>; '
        f'labelloc="t"; fontcolor="#b58900";\n'
        if banner else ""
    )
    dot = [
        'digraph Methodology {',
        '  rankdir=LR; bgcolor="white"; pad=0.4;',
        '  nodesep=0.35; ranksep=0.7; fontname="Helvetica"; compound=true;',
        '  node [shape=box style="rounded,filled" fontname="Helvetica" '
        '       fontsize=11 margin="0.14,0.08"];',
        f'  edge [color="{EDGE_BLUE}" fontsize=9 fontname="Helvetica"];',
        label_attr,
    ]

    # ----- Column 1: input + decomposition -----
    dot.append('subgraph cluster_in {')
    dot.append('  label="1. Split the work"; labeljust="l";')
    dot.append('  style="rounded,filled"; fillcolor="#fffbe6"; color="#b58900";')
    dot.append('  fontname="Helvetica-Bold"; fontsize=12;')
    if state.get("user"):
        prompt_text = state.get("prompt") or "Design a bridge for<BR/>50 cars/h \u2014 modern"
        dot.append(
            f'  user [label=<<B>User prompt</B><BR/>'
            f'<I>\u201c{prompt_text}\u201d</I>>, shape=note '
            f'fillcolor="{COL_USER[0]}" color="{COL_USER[1]}"];'
        )
    if state.get("orch"):
        # Pulse the orchestrator border on backward phase (amber).
        col = PULSE_AMBER if state.get("pulse_back") else COL_ORCH[1]
        pen = 3 if state.get("pulse_back") else 1
        dot.append(
            f'  orch [label="Orchestrator (LLM)\\n'
            f'splits the work,\\ninteracts with marshals", '
            f'fillcolor="{COL_ORCH[0]}" color="{col}" penwidth={pen}];'
        )
    for tag, col in [("t1", COL_T1), ("t2", COL_T2), ("t3", COL_T3)]:
        if state.get(tag):
            dot.append(
                f'  {tag} [label="{tag.upper()}" fillcolor="{col[0]}" color="{col[1]}"];'
            )
    if state.get("user") and state.get("orch"):
        dot.append('  user -> orch;')
    if state.get("orch"):
        for tag in ("t1", "t2", "t3"):
            if state.get(tag):
                dot.append(f'  orch -> {tag};')
    dot.append('}')

    # ----- Column 2: skills DB (semantic search + Shapley) -----
    dot.append('subgraph cluster_mkt {')
    dot.append('  label="2. Semantic search over the skills DB"; labeljust="l";')
    dot.append('  style="rounded,filled"; fillcolor="#f0fff0"; color="#2f7a2f";')
    dot.append('  fontname="Helvetica-Bold"; fontsize=12;')
    if state.get("market"):
        dot.append(
            f'  market [label="100,000 skills (skills.sh)\\n'
            f'vector-indexed by capability", shape=cylinder '
            f'fillcolor="{COL_MKT_CYL[0]}" color="{COL_MKT_CYL[1]}" fontsize=12];'
        )
    if state.get("find"):
        dot.append(
            f'  find [label="Find candidates\\n(RAG over skills DB)" '
            f'fillcolor="{COL_MKT_BOX[0]}" color="{COL_MKT_BOX[1]}"];'
        )
    if state.get("filt"):
        dot.append(
            f'  filt [label="Score by marginal fit\\n'
            f'(Shapley contribution)" '
            f'fillcolor="{COL_MKT_BOX[0]}" color="{COL_MKT_BOX[1]}"];'
        )
    if state.get("pick"):
        dot.append(
            f'  pick [label="Pick the smallest team\\n'
            f'that covers everything" '
            f'fillcolor="{COL_MKT_BOX[0]}" color="{COL_MKT_BOX[1]}"];'
        )
    if state.get("market") and state.get("find"):
        dot.append('  market -> find [style=invis];')
    if state.get("find") and state.get("filt"):
        dot.append('  find -> filt;')
    if state.get("filt") and state.get("pick"):
        dot.append('  filt -> pick;')
    dot.append('}')

    # ----- Column 3: three teams -----
    for name in ("T1", "T2", "T3"):
        fill, border, a2a, cluster_fill = TEAM_COLORS[name]
        dot.append(
            _team_cluster(
                name, state, fill, border, a2a, cluster_fill,
                pulse_marshal_to_orch=state.get("pulse_back", False),
                pulse_agents_to_marshal=state.get("pulse_back", False),
            )
        )

    # ----- Cross-column wiring -----
    if state.get("t1") and state.get("find"):
        dot.append('t1 -> find [label="needed\\nskills" lhead=cluster_mkt];')

    # Marketplace -> marshals
    pulse = state.get("pulse_back", False)
    edge_col = PULSE_AMBER if pulse else EDGE_BLUE
    pen = 3 if pulse else 1
    for name in ("T1", "T2", "T3"):
        marshal_id = f"m{name[1]}"
        if state.get("pick") and state.get(f"marshal_{name}"):
            dot.append(
                f'pick -> {marshal_id} [label="team {name}" '
                f'ltail=cluster_mkt color="{edge_col}" penwidth={pen}];'
            )

    # Backward pulse: marshals -> orchestrator (only on the pulse frames).
    if pulse and state.get("orch"):
        for name in ("T1", "T2", "T3"):
            marshal_id = f"m{name[1]}"
            if state.get(f"marshal_{name}"):
                dot.append(
                    f'{marshal_id} -> orch [color="{PULSE_AMBER}" '
                    f'penwidth=3 style=dashed constraint=false];'
                )

    # Final design brief.
    if state.get("brief"):
        dot.append(
            f'brief [label="Design brief\\n(report + 3D + cost)", '
            f'fillcolor="{COL_BRIEF[0]}" color="{COL_BRIEF[1]}"];'
        )
        for name in ("T1", "T2", "T3"):
            last_agent = TEAM_AGENTS[name][-1][0]
            if state.get(f"agent_{last_agent}"):
                dot.append(f'{last_agent} -> brief [style=dashed];')

    dot.append('}')
    return "\n".join(dot)


def build_frames() -> list[dict]:
    """Build the cumulative state for each frame.

    Forward phase: ~14 frames at ~0.35 s each = ~4.9 s.
    Backward pulse: 2 frames at 0.4 s = 0.8 s.
    Hold (full diagram): 4 frames at 0.3 s = 1.2 s.
    Total: ~7 s.
    """
    state: dict = {}
    frames: list[dict] = []

    def snap(**kwargs):
        state.update(kwargs)
        frames.append(dict(state))

    # Forward build.
    snap(user=True)
    snap(orch=True)
    snap(t1=True)
    snap(t2=True, t3=True)
    snap(market=True)
    snap(find=True)
    snap(filt=True)
    snap(pick=True)
    snap(marshal_T1=True)
    snap(marshal_T2=True, marshal_T3=True)
    snap(agent_a1a=True, agent_a1b=True, agent_a1c=True)
    snap(agent_a2a=True, agent_a2b=True, agent_a2c=True)
    snap(agent_a3a=True, agent_a3b=True, agent_a3c=True)
    snap(a2a_T1=True, a2a_T2=True, a2a_T3=True)

    # Backward pulse (2 frames) + design brief reveal.
    snap(pulse_back=True)
    snap(pulse_back=True, brief=True)

    # Hold: pulse off, full diagram visible (4 frames).
    state["pulse_back"] = False
    for _ in range(4):
        frames.append(dict(state))

    # Prompt-swap showcase: same diagram, different user prompt.
    # Demonstrates that the same pipeline works across domains.
    snap(prompt="Design a bridge for<BR/>50 cars/h \u2014 modern",
         banner="Same pipeline. Any domain.")
    snap(prompt="Design a roller coaster<BR/>for 50 people \u2014 modern",
         banner="Same pipeline. Any domain.")
    snap(prompt="Design an airplane<BR/>for 200 people",
         banner="Same pipeline. Any domain.")

    return frames


def render_frame(state: dict, out_path: Path) -> None:
    """Render one frame to PNG via the `dot` CLI."""
    import subprocess
    dot_src = render_dot(state)
    dot_file = out_path.with_suffix(".dot")
    dot_file.write_text(dot_src)
    subprocess.run(
        ["dot", "-Tpng", "-Gdpi=110", str(dot_file), "-o", str(out_path)],
        check=True,
    )
    dot_file.unlink()


def main() -> None:
    frames_state = build_frames()
    print(f"[methodology-anim] {len(frames_state)} frames")

    # Per-frame durations (seconds). Forward phase has variable timing so
    # the early "scaffold" frames are shorter than the team reveals.
    durations: list[float] = []
    n_forward = len(frames_state) - 9  # last 3 = prompt swaps, 4 = hold, 2 = pulse
    durations.extend([1.10] * n_forward)   # forward build: each step held ~1.1 s
    durations.extend([1.60] * 2)           # pulse frames: held longer for emphasis
    durations.extend([1.30] * 4)           # hold frames: full diagram visible
    durations.extend([3.00] * 3)           # prompt-swap showcase: each held 3 s

    with TemporaryDirectory() as td:
        td_path = Path(td)
        png_paths: list[Path] = []
        for i, st in enumerate(frames_state):
            png = td_path / f"frame_{i:03d}.png"
            render_frame(st, png)
            png_paths.append(png)
            print(f"  frame {i+1}/{len(frames_state)}  ok")

        # ----- Pad every frame to the same canvas size (=last frame) so
        # GIF/MP4 don't jitter.
        last = Image.open(png_paths[-1])
        canvas_w, canvas_h = last.size
        # libx264 requires even dimensions; round up.
        if canvas_w % 2:
            canvas_w += 1
        if canvas_h % 2:
            canvas_h += 1
        padded_paths: list[Path] = []
        for i, p in enumerate(png_paths):
            img = Image.open(p).convert("RGBA")
            bg = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
            bg.paste(img, ((canvas_w - img.width) // 2,
                           (canvas_h - img.height) // 2), img)
            out = td_path / f"padded_{i:03d}.png"
            bg.convert("RGB").save(out)
            padded_paths.append(out)

        # ----- Build GIF via PIL directly (imageio's GIF plugin silently
        # ignores per-frame duration lists in some versions). PIL accepts
        # duration in milliseconds, either as a single int or per-frame list.
        gif_path = OUT_DIR / "VID-2-methodology.gif"
        pil_frames = [Image.open(p).convert("RGB") for p in padded_paths]
        durations_ms = [int(d * 1000) for d in durations]
        pil_frames[0].save(
            gif_path,
            save_all=True,
            append_images=pil_frames[1:],
            duration=durations_ms,
            loop=0,
            optimize=False,
            disposal=2,
        )
        size_kb = gif_path.stat().st_size // 1024
        total_s = sum(durations_ms) / 1000
        print(f"[methodology-anim] wrote {gif_path}  ({size_kb} KB), ~{total_s:.1f}s")

        # ----- Build MP4 via imageio-ffmpeg. Use a constant base fps
        # and duplicate frames per their per-frame duration to honour
        # variable timing (poor man's concat demuxer).
        base_fps = 4  # 0.25 s resolution
        mp4_path = OUT_DIR / "VID-2-methodology.mp4"
        writer = imageio.get_writer(
            mp4_path, fps=base_fps, codec="libx264",
            quality=8, macro_block_size=None,
        )
        for p, d in zip(padded_paths, durations):
            img = imageio.imread(p)
            reps = max(1, round(d * base_fps))
            for _ in range(reps):
                writer.append_data(img)
        writer.close()
        size_kb = mp4_path.stat().st_size // 1024
        total = sum(max(1, round(d * base_fps)) for d in durations) / base_fps
        print(f"[methodology-anim] wrote {mp4_path}  ({size_kb} KB) @ {base_fps} fps, ~{total:.1f}s")


if __name__ == "__main__":
    main()
