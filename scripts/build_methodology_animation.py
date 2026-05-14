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
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "social"
OUT_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR = OUT_DIR / "img"

# (prompt text, image path, banner)
RESULT_FRAMES = [
    ("Design a bridge for 50 cars/h \u2014 modern",
     IMG_DIR / "bridge.png",
     "Same pipeline. Any domain."),
    ("Design a roller coaster for 50 people \u2014 modern",
     IMG_DIR / "rollercoaster.png",
     "Same pipeline. Any domain."),
    ("Design an airplane for 200 people",
     IMG_DIR / "airplane.png",
     "Same pipeline. Any domain."),
]


def _load_font(size: int) -> ImageFont.ImageFont:
    """Best-effort load of a system font; fall back to default bitmap."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def compose_result_frame(prompt: str, image_path: Path, banner: str,
                         canvas_w: int, canvas_h: int) -> Image.Image:
    """Compose a result frame: banner + prompt on top, big image below,
    footer note pinned to the bottom. Content is laid out in a centered
    column so the image stays large even on a wide diagram canvas.
    """
    bg = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(bg)
    margin_v = 24

    # Working column width: at most 1.5x the height (squarer than the
    # wide diagram canvas) so the rendered image isn't dwarfed.
    col_w = min(canvas_w - 80, int(canvas_h * 1.6))
    col_x = (canvas_w - col_w) // 2

    # Banner (top, amber).
    banner_font = _load_font(40)
    bw, bh = draw.textbbox((0, 0), banner, font=banner_font)[2:]
    draw.text(((canvas_w - bw) // 2, 16), banner,
              fill="#b58900", font=banner_font)
    y = 16 + bh + 12

    # Prompt (centered, quoted, big, word-wrapped to column width).
    prompt_font = _load_font(34)
    quoted = f"\u201c{prompt}\u201d"
    words = quoted.split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = (current + " " + w).strip()
        if draw.textbbox((0, 0), candidate, font=prompt_font)[2] > col_w and current:
            lines.append(current)
            current = w
        else:
            current = candidate
    if current:
        lines.append(current)
    line_h = draw.textbbox((0, 0), "Ag", font=prompt_font)[3] + 6
    for line in lines:
        lw = draw.textbbox((0, 0), line, font=prompt_font)[2]
        draw.text(((canvas_w - lw) // 2, y), line,
                  fill="#5c4400", font=prompt_font)
        y += line_h
    y += 10

    # Footer note pinned to the bottom.
    note_text = "Full technical spec + report in the run trace."
    note_font = _load_font(22)
    nw, nh = draw.textbbox((0, 0), note_text, font=note_font)[2:]
    note_y = canvas_h - margin_v - nh

    # Rendered image fills the centered column, full available height.
    img_top = y
    img_bottom = note_y - 24
    img_box_w = col_w
    img_box_h = img_bottom - img_top
    if image_path.exists() and img_box_h > 50:
        img = Image.open(image_path).convert("RGB")
        # Scale up if needed (PIL.thumbnail only shrinks).
        scale = min(img_box_w / img.width, img_box_h / img.height)
        new_size = (max(1, int(img.width * scale)),
                    max(1, int(img.height * scale)))
        img = img.resize(new_size, Image.LANCZOS)
        ix = (canvas_w - img.width) // 2
        iy = img_top + (img_box_h - img.height) // 2
        bg.paste(img, (ix, iy))
    elif not image_path.exists():
        miss_font = _load_font(28)
        draw.text((col_x, img_top + 20),
                  f"(missing: {image_path.name})",
                  fill="#888888", font=miss_font)

    draw.text(((canvas_w - nw) // 2, note_y), note_text,
              fill="#888888", font=note_font)

    return bg

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
        '       fontsize=22 margin="0.22,0.14"];',
        f'  edge [color="{EDGE_BLUE}" fontsize=16 fontname="Helvetica"];',
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
    """Build the list of animation frames (dicts with state and timing).

    Forward phase: ~14 frames at ~0.35 s each = ~4.9 s.
    Backward pulse: 2 frames at 0.4 s = 0.8 s.
    Hold (full diagram): 4 frames at 0.3 s = 1.2 s.
    Total: ~7 s.

    Returns:
        list[dict]: Animation frames with state and timing.
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

    return frames


def render_frame(state: dict, out_path: Path) -> None:
    """Render a single animation frame to an image file.

    Args:
        state: Animation state dict.
        out_path: Output image file path.
    """
    import subprocess
    dot_src = render_dot(state)
    dot_file = out_path.with_suffix(".dot")
    dot_file.write_text(dot_src)
    subprocess.run(
        ["dot", "-Tpng", "-Gdpi=130", str(dot_file), "-o", str(out_path)],
        check=True,
    )
    dot_file.unlink()


def main() -> None:
    """Entry point: build and export the animation.

    Returns:
        None
    """
    frames_state = build_frames()
    print(f"[methodology-anim] {len(frames_state)} frames")

    # Per-frame durations (seconds). Forward phase has variable timing so
    # the early "scaffold" frames are shorter than the team reveals.
    durations: list[float] = []
    n_forward = len(frames_state) - 6  # last 4 = hold, 2 = pulse
    durations.extend([1.10] * n_forward)   # forward build: each step held ~1.1 s
    durations.extend([1.60] * 2)           # pulse frames: held longer for emphasis
    durations.extend([1.30] * 4)           # hold frames: full diagram visible

    with TemporaryDirectory() as td:
        td_path = Path(td)
        png_paths: list[Path] = []
        for i, st in enumerate(frames_state):
            png = td_path / f"frame_{i:03d}.png"
            render_frame(st, png)
            png_paths.append(png)
            print(f"  frame {i+1}/{len(frames_state)}  ok")

        # ----- Pad every frame to a fixed 16:9 canvas (1920x1080) so the
        # output is Twitter/X-compatible. Each rendered diagram or result
        # frame is scaled to fit and centered with white letterboxing.
        canvas_w, canvas_h = 1920, 1080

        def fit_to_canvas(src_path: Path) -> Image.Image:
            src = Image.open(src_path).convert("RGB")
            scale = min(canvas_w / src.width, canvas_h / src.height)
            new_size = (max(1, int(src.width * scale)),
                        max(1, int(src.height * scale)))
            scaled = src.resize(new_size, Image.LANCZOS)
            bg = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
            bg.paste(scaled, ((canvas_w - scaled.width) // 2,
                              (canvas_h - scaled.height) // 2))
            return bg

        padded_paths: list[Path] = []
        for i, p in enumerate(png_paths):
            out = td_path / f"padded_{i:03d}.png"
            fit_to_canvas(p).save(out)
            padded_paths.append(out)

        # ----- Result frames: prompt + actual rendered output for each domain.
        # Composed directly on the 1920x1080 canvas.
        for j, (prompt, img_path, banner) in enumerate(RESULT_FRAMES):
            frame = compose_result_frame(prompt, img_path, banner,
                                         canvas_w, canvas_h)
            out = td_path / f"result_{j:03d}.png"
            frame.save(out)
            padded_paths.append(out)
            durations.append(3.50)
            print(f"  result frame {j+1}/{len(RESULT_FRAMES)}  ok ({img_path.name})")

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

        # ----- Build MP4 via imageio-ffmpeg. Use a 30 fps base (Twitter
        # rejects ultra-low frame-rate clips) and duplicate frames per
        # their per-frame duration. Output yuv420p so it plays in every
        # browser/social-media client.
        base_fps = 30
        mp4_path = OUT_DIR / "VID-2-methodology.mp4"
        writer = imageio.get_writer(
            mp4_path, fps=base_fps, codec="libx264",
            quality=8, macro_block_size=None,
            ffmpeg_params=["-pix_fmt", "yuv420p", "-profile:v", "high",
                           "-level", "4.0"],
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
