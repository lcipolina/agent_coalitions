"""Spec -> generic 3D geometry primitives (Visualiser agent).

Pipeline stage. The job is to translate the synthesised design spec
(whose JSON schema is domain-dependent) into a uniform list of
domain-agnostic primitives (boxes + polylines) that the renderer
(``src.ui.render3d``) can draw without any domain knowledge.

There are two execution paths:

* **Mock mode** (``USE_MOCK_LLM=true``, the demo default). Runs a
  deterministic Python builder that knows the bridge spec schema
  (`total_length_m`, `span_layout`, `deck_width_m`, `bridge_type`, ...).
  Fast, offline, reproducible.

* **Real mode**. Calls ``chat(role="visualiser")`` with the spec and
  the primitive schema. The LLM is the right tool here precisely
  because different design domains (bridge, rollercoaster, tower, dam)
  produce different spec schemas, and a hand-written Python switch
  cannot scale to all of them. The LLM output is parsed and validated;
  on any parse / validation failure, the deterministic bridge builder
  is used as a fallback so the pipeline never crashes mid-demo.

Either way the result is persisted as an ``artifacts`` row of kind
``geometry_json``, making the picture replayable like every other
artifact.

Primitive schema::

    {"kind": "box",  "x": [x0,x1], "y": [y0,y1], "z": [z0,z1],
     "color": "#hex", "name": "deck"}
    {"kind": "line", "points": [[x,y,z], ...],
     "color": "rgba(...)", "width": 2.0, "name": "cable_3_2"}

Coordinate convention: x along structure length, y across width, z up.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.core.config import settings
from src.db.client import get_db
from src.db.writes import insert_with_event
from src.llm.openai_client import chat
from src.llm.prompts import render

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------
def _box(x0: float, x1: float, y0: float, y1: float,
         z0: float, z1: float, color: str, name: str) -> dict[str, Any]:
    return {"kind": "box",
            "x": [x0, x1], "y": [y0, y1], "z": [z0, z1],
            "color": color, "name": name}


def _line(points: list[list[float]], color: str,
          width: float, name: str) -> dict[str, Any]:
    return {"kind": "line", "points": points,
            "color": color, "width": width, "name": name}


def _support_xs(spec: dict) -> list[float]:
    xs: list[float] = [0.0]
    x = 0.0
    for s in spec.get("span_layout") or []:
        x += float(s.get("length_m", 0))
        xs.append(x)
    return xs


def _bridge_primitives(spec: dict[str, Any]) -> dict[str, Any]:
    """Deterministic bridge-spec -> geometry. Used in mock mode and as the
    real-mode fallback when the LLM output cannot be parsed or validated."""
    L = float(spec.get("total_length_m") or
              sum((s.get("length_m", 0) for s in spec.get("span_layout") or []), 0)
              or 1000.0)
    W = float(spec.get("deck_width_m") or 12.0)
    longest = max((s.get("length_m", 0)
                   for s in spec.get("span_layout") or []), default=L)
    deck_t = float(spec.get("structural_depth_m") or max(longest / 80.0, 1.2))
    pier_h = max(longest / 14.0, L * 0.012, 6.0)
    z_deck = pier_h
    pier_w = max(L * 0.008, 1.5)

    prims: list[dict[str, Any]] = []

    # Banks (shore strips on each side of the river) — visible reference
    # so the deck doesn't look like it's floating on infinite water.
    bank_w = max(L * 0.06, 6.0)
    for x_a, x_b, name in (
        (-bank_w, 0.0, "bank_west"),
        (L, L + bank_w, "bank_east"),
    ):
        prims.append(_box(
            x_a, x_b, -W * 1.6, W * 1.6,
            -0.05, max(z_deck * 0.05, 0.4),
            "#9aa089", name,
        ))

    # Deck
    prims.append(_box(0.0, L, -W / 2, W / 2,
                      z_deck, z_deck + deck_t,
                      "#2c2c2c", "deck"))

    # Parapet / edge beams running the full length on each side of the
    # deck — a small detail that gives the deck visible depth and stops
    # the default-girder bridge from looking like a bare slab.
    parapet_h = max(deck_t * 0.6, 0.6)
    for ys, y_e, name in (
        (-W / 2, -W / 2 + max(W * 0.04, 0.3), "parapet_left"),
        (W / 2 - max(W * 0.04, 0.3), W / 2, "parapet_right"),
    ):
        prims.append(_box(
            0.0, L, ys, y_e,
            z_deck + deck_t, z_deck + deck_t + parapet_h,
            "#bfbfbf", name,
        ))

    # Abutments at each bank — short, wide blocks under the deck ends.
    abut_x = max(L * 0.02, 2.0)
    for x_a, x_b, name in (
        (-abut_x * 0.5, abut_x, "abutment_west"),
        (L - abut_x, L + abut_x * 0.5, "abutment_east"),
    ):
        prims.append(_box(
            x_a, x_b, -W * 0.55, W * 0.55,
            0.0, z_deck,
            "#8a8a8a", name,
        ))

    # Piers (intermediate supports only — the abutments cover the ends)
    xs = _support_xs(spec) or [0.0, L]
    interior_xs = [xp for xp in xs if 0.0 < xp < L]
    for xp in interior_xs:
        prims.append(_box(
            xp - pier_w / 2, xp + pier_w / 2,
            -W * 0.30, W * 0.30,
            0.0, z_deck,
            "#7a7a7a", f"pier@{int(xp)}m",
        ))

    btype = (spec.get("bridge_type") or "").lower()

    # Pylons + fanned stay cables (twin planes left/right of deck centre)
    if "cable" in btype and "stay" in btype and len(xs) >= 3:
        pylon_h = max(L * 0.05, pier_h * 1.6)
        for i in range(1, len(xs) - 1, 2):
            xp = xs[i]
            top_z = z_deck + pylon_h
            prims.append(_box(
                xp - pier_w * 0.4, xp + pier_w * 0.4,
                -W * 0.06, W * 0.06,
                z_deck, top_z,
                "#d35400", f"pylon@{int(xp)}m",
            ))
            span_back = xp - xs[i - 1] if i > 0 else L / max(len(xs) - 1, 1)
            span_fwd = xs[i + 1] - xp if i + 1 < len(xs) else L / max(len(xs) - 1, 1)
            for k in range(1, 7):
                frac = k / 7
                for sign, sp in ((-1.0, span_back), (1.0, span_fwd)):
                    xd = xp + sign * frac * sp
                    for ys in (-W * 0.40, W * 0.40):
                        prims.append(_line(
                            [[xp, ys, top_z],
                             [xd, ys, z_deck + deck_t]],
                            "rgba(40,40,40,0.65)", 1.5,
                            f"cable_{i}_{k}_{int(sign)}_{int(ys)}",
                        ))

    elif "suspension" in btype and len(xs) >= 2:
        x0, x1 = xs[0], xs[-1]
        xL = x0 + 0.25 * (x1 - x0)
        xR = x0 + 0.75 * (x1 - x0)
        tower_h = max(L * 0.06, pier_h * 1.8)
        top_z = z_deck + tower_h
        for xt in (xL, xR):
            prims.append(_box(
                xt - pier_w * 0.4, xt + pier_w * 0.4,
                -W * 0.06, W * 0.06,
                z_deck, top_z,
                "#d35400", f"tower@{int(xt)}m",
            ))
        sag = (xR - xL) * 0.18
        for ys in (-W * 0.40, W * 0.40):
            n = 24
            mid: list[list[float]] = []
            for k in range(n):
                u = k / (n - 1)
                x = xL + u * (xR - xL)
                z = top_z - sag * 4 * u * (1 - u)
                mid.append([x, ys, z])
            pts = [[x0, ys, z_deck + deck_t]] + mid + [[x1, ys, z_deck + deck_t]]
            prims.append(_line(pts, "rgba(40,40,40,0.85)", 2.5,
                               f"main_cable_{int(ys)}"))
            # vertical hangers
            for k in range(2, n - 1, 3):
                prims.append(_line(
                    [[mid[k][0], ys, z_deck + deck_t], mid[k]],
                    "rgba(40,40,40,0.55)", 1.0,
                    f"hanger_{k}_{int(ys)}",
                ))

    elif "arch" in btype and len(xs) >= 2:
        x0, x1 = xs[0], xs[-1]
        rise = (x1 - x0) * 0.18
        n = 36
        for ys in (-W * 0.35, W * 0.35):
            pts: list[list[float]] = []
            for k in range(n):
                u = k / (n - 1)
                xa = x0 + u * (x1 - x0)
                za = z_deck * 0.1 + rise * 4 * u * (1 - u)
                pts.append([xa, ys, za])
            prims.append(_line(pts, "#a85a3c", 5.0, f"arch_{int(ys)}"))
            # spandrel verticals up to the deck
            for k in range(4, n - 4, 4):
                prims.append(_line(
                    [pts[k], [pts[k][0], ys, z_deck]],
                    "#a85a3c", 2.0, f"spandrel_{k}_{int(ys)}",
                ))

    elif "truss" in btype:
        truss_h = max(deck_t * 4, 6.0)
        top_z = z_deck + deck_t + truss_h
        for ys in (-W * 0.45, W * 0.45):
            prims.append(_line(
                [[xs[0], ys, top_z], [xs[-1], ys, top_z]],
                "#555555", 3.0, f"top_chord_{int(ys)}",
            ))
            for i in range(len(xs) - 1):
                xa, xb = xs[i], xs[i + 1]
                n_panels = 6
                for kk in range(n_panels):
                    p0 = xa + (xb - xa) * (kk / n_panels)
                    p1 = xa + (xb - xa) * ((kk + 1) / n_panels)
                    if kk % 2 == 0:
                        prims.append(_line(
                            [[p0, ys, z_deck + deck_t], [p1, ys, top_z]],
                            "#555555", 1.5, f"diag_{i}_{kk}_{int(ys)}",
                        ))
                    else:
                        prims.append(_line(
                            [[p0, ys, top_z], [p1, ys, z_deck + deck_t]],
                            "#555555", 1.5, f"diag_{i}_{kk}_{int(ys)}",
                        ))
                for kk in range(n_panels + 1):
                    px = xa + (xb - xa) * (kk / n_panels)
                    prims.append(_line(
                        [[px, ys, z_deck + deck_t], [px, ys, top_z]],
                        "#555555", 1.0, f"vert_{i}_{kk}_{int(ys)}",
                    ))

    # Water plane (for atmosphere) — a thin, low-opacity box at z=0
    prims.append(_box(
        -L * 0.05, L * 1.05,
        -W * 1.5, W * 1.5,
        -0.3, 0.0,
        "rgba(70,120,180,0.35)", "water",
    ))

    geometry = {
        "primitives": prims,
        "title": (f"{spec.get('bridge_type', 'structure').replace('_', ' ').title()} "
                  f"· {int(L)} m total · longest span {int(longest)} m"),
        "axes": {"x": "length (m)", "y": "width (m)", "z": "height (m)"},
        "extent": {
            "x": [-bank_w, L + bank_w],
            "y": [-W * 1.6, W * 1.6],
            "z": [-1.0, z_deck * 4],
        },
    }
    return geometry


def _generic_primitives(spec: dict[str, Any]) -> dict[str, Any]:
    """Domain-agnostic geometry fallback for non-bridge specs.

    Produces a coarse but legible 3D massing study from the spec's
    ``dimensions`` (length × width × height), plus a couple of vertical
    members and a ground plane. Used when the spec is clearly not a
    bridge and the LLM path is unavailable or fails.
    """
    dims = spec.get("dimensions") or {}
    L = float(dims.get("length_m") or 100.0)
    W = float(dims.get("width_m") or 20.0)
    H = float(dims.get("height_m") or 30.0)
    domain = (spec.get("domain") or "").lower()
    dtype = (spec.get("design_type") or "").lower()

    prims: list[dict[str, Any]] = []
    # Ground plane.
    prims.append(_box(-L * 0.1, L * 1.1, -W * 1.5, W * 1.5,
                      -0.3, 0.0, "rgba(110,150,110,0.35)", "ground"))

    if "rollercoaster" in domain or "coaster" in dtype or "rollercoaster" in dtype:
        # Track recipe: long horizontal sweep with one big hill, one true
        # vertical loop-the-loop and one helical curve in plan. The loop
        # is a circle in the x-z plane; we trace x = xc + R*sin(t),
        # z = zc + R*(1 - cos(t)) so the rail leaves the ground tangentially
        # at t=0, peaks at t=pi above the ground, and rejoins at t=2pi.
        import math
        rail_offset = 0.6
        # Loop geometry. Pin the loop's lowest point to z = 1.5 so the
        # rail enters tangentially from track level instead of dipping
        # below the ground plane.
        loop_R = max(min(H * 0.40, L * 0.10), 6.0)
        loop_xc = L * 0.50
        loop_zc = loop_R + 1.5
        # Sample positions along the track.
        # Phase 0 [0..0.30]: lift hill (climbs from ~0 to H*0.85, then
        #                     dives back to H*0.20) along x in [0, 0.30 L].
        # Phase 1 [0.30..0.50]: straight approach into the loop.
        # Phase 2 [loop]:       full vertical circle around (loop_xc, loop_zc).
        # Phase 3 [0.55..0.80]: helical S-curve back along x.
        # Phase 4 [0.80..1.0]:  brake run into station.
        track: list[tuple[float, float, float]] = []
        # Phase 0 — hill.
        for k in range(60):
            u = k / 59
            x = u * L * 0.30
            z = H * 0.85 * math.sin(u * math.pi)        # up then down
            y = W * 0.20 * math.sin(u * math.pi * 0.5)
            track.append((x, y, max(z, 1.5)))
        # Phase 1 — straight approach.
        approach_z = max(loop_zc - loop_R + 1.5, 1.5)
        for k in range(20):
            u = k / 19
            x = L * 0.30 + u * (loop_xc - loop_R - L * 0.30)
            track.append((x, 0.0, approach_z))
        # Phase 2 — true vertical loop in x-z plane.
        for k in range(72):
            t = (k / 71) * 2 * math.pi
            x = loop_xc - loop_R * math.cos(t)            # enters from -x side
            z = loop_zc + loop_R * math.sin(t)
            # Lift the loop slightly so it never dips below ground.
            track.append((x, 0.0, max(z, 1.5)))
        # Phase 3 — helical S-curve.
        x_start = loop_xc + loop_R
        x_end = L * 0.85
        for k in range(60):
            u = k / 59
            x = x_start + u * (x_end - x_start)
            y = W * 0.45 * math.sin(u * math.pi * 2)       # weave left-right
            z = H * 0.35 + H * 0.20 * math.cos(u * math.pi * 3)
            track.append((x, y, max(z, 1.5)))
        # Phase 4 — brake run / return to station.
        for k in range(30):
            u = k / 29
            x = x_end + u * (L - x_end)
            y = W * 0.45 * (1 - u) * math.cos(u * math.pi)
            z = max(H * 0.10 * (1 - u) + 1.5, 1.5)
            track.append((x, y, z))
        # Twin rails: offset in y perpendicular to the local tangent so the
        # two rails always sit either side of the centreline.
        for sign in (-1.0, 1.0):
            pts: list[list[float]] = []
            for i, (x, y, z) in enumerate(track):
                # Local tangent in x-y plane.
                if i + 1 < len(track):
                    dx = track[i + 1][0] - x
                    dy = track[i + 1][1] - y
                else:
                    dx = x - track[i - 1][0]
                    dy = y - track[i - 1][1]
                norm = math.hypot(dx, dy) or 1.0
                # Perpendicular in plan = (-dy, dx) / norm.
                ox = -dy / norm * rail_offset * sign
                oy = dx / norm * rail_offset * sign
                pts.append([x + ox, y + oy, z])
            prims.append(_line(pts, "#c0392b", 4.0, f"rail_{int(sign)}"))
        # Crossties every ~6 m of arc length (visual "ladder rungs").
        # Step through the centreline track and drop a small box bridging
        # the two rails.
        for i in range(0, len(track), 4):
            x, y, z = track[i]
            if i + 1 < len(track):
                dx = track[i + 1][0] - x
                dy = track[i + 1][1] - y
            else:
                continue
            norm = math.hypot(dx, dy) or 1.0
            ox = -dy / norm * rail_offset
            oy = dx / norm * rail_offset
            prims.append(_box(min(x - ox, x + ox) - 0.1,
                              max(x - ox, x + ox) + 0.1,
                              min(y - oy, y + oy) - 0.1,
                              max(y - oy, y + oy) + 0.1,
                              z - 0.15, z + 0.15,
                              "#7d3c0e", f"tie_{i}"))
        # Support columns roughly every 25 m of x along the lift hill and
        # brake run (skip the loop interior so columns don't pierce the
        # vertical circle).
        for xc in range(20, int(L) - 5, 25):
            # Skip near the loop.
            if abs(xc - loop_xc) < loop_R * 1.1:
                continue
            # Find nearest track point above this xc to size the column.
            zc = max(
                (z for (x, _y, z) in track if abs(x - xc) < 6),
                default=H * 0.4,
            )
            prims.append(_box(xc - 0.6, xc + 0.6, -0.6, 0.6,
                              0.0, max(zc - 0.5, 2.0),
                              "#7a7a7a", f"support_{xc}"))
        # Station building.
        prims.append(_box(0.0, L * 0.08, -W * 0.4, W * 0.4,
                          0.0, H * 0.25, "#34495e", "station"))
        title = (f"{(spec.get('design_type') or 'rollercoaster').replace('_', ' ')}"
                 f" · {int(L)} m track · {int(H)} m max height")
    elif "tower" in domain or "tower" in dtype or "skyscraper" in dtype \
            or "building" in domain or "building" in dtype:
        # Stacked floor-plates with a vertical core.
        floors = max(int(H // 4), 1)
        for f in range(floors):
            z0 = f * H / floors
            z1 = (f + 1) * H / floors
            colour = "#566573" if f % 2 == 0 else "#34495e"
            prims.append(_box(-W / 2, W / 2, -W / 2, W / 2,
                              z0, z1, colour, f"floor_{f + 1}"))
        # Core.
        prims.append(_box(-W * 0.12, W * 0.12, -W * 0.12, W * 0.12,
                          0.0, H, "#1c2833", "core"))
        title = (f"{(spec.get('design_type') or 'tower').replace('_', ' ')} · "
                 f"{int(H)} m tall · {int(W)} m × {int(W)} m footprint")
    elif "pavilion" in domain or "pavilion" in dtype:
        # Wide low pavilion: a roof box on slim columns.
        roof_t = max(H * 0.08, 0.6)
        prims.append(_box(0.0, L, -W / 2, W / 2,
                          H - roof_t, H, "#d4a574", "roof"))
        # Columns at corners + midpoints.
        for xc in (L * 0.05, L * 0.5, L * 0.95):
            for yc in (-W * 0.4, W * 0.4):
                prims.append(_box(xc - 0.4, xc + 0.4, yc - 0.4, yc + 0.4,
                                  0.0, H - roof_t, "#7a7a7a",
                                  f"column_{int(xc)}_{int(yc)}"))
        title = (f"{(spec.get('design_type') or 'pavilion').replace('_', ' ')} · "
                 f"{int(L)} m × {int(W)} m · {int(H)} m roof")
    else:
        # Generic massing block.
        prims.append(_box(0.0, L, -W / 2, W / 2,
                          0.0, H, "#7f8c8d", "mass"))
        title = (f"{(spec.get('design_type') or 'structure').replace('_', ' ')} · "
                 f"{int(L)} × {int(W)} × {int(H)} m envelope")

    return {
        "primitives": prims,
        "title": title,
        "axes": {"x": "length (m)", "y": "width (m)", "z": "height (m)"},
        "extent": {"x": [0.0, L], "y": [-W, W], "z": [-1.0, H * 1.2]},
    }


def _spec_looks_like_bridge(spec: dict[str, Any]) -> bool:
    keys = {"span_layout", "deck_width_m", "bridge_type",
            "total_length_m", "design_live_load_kN_per_m"}
    has_keys = sum(1 for k in keys if spec.get(k))
    domain = (spec.get("domain") or "").lower()
    return domain == "bridge" or has_keys >= 3


def _deterministic_primitives(spec: dict[str, Any]) -> dict[str, Any]:
    """Dispatch deterministic geometry on whether the spec is a bridge."""
    if _spec_looks_like_bridge(spec):
        return _bridge_primitives(spec)
    return _generic_primitives(spec)


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------
ALLOWED_KINDS = {"box", "line"}


def _validate_geometry(data: Any) -> dict[str, Any]:
    """Minimal schema check on LLM output. Raises ValueError on any issue."""
    if not isinstance(data, dict):
        raise ValueError("top-level must be an object")
    prims = data.get("primitives")
    if not isinstance(prims, list) or not prims:
        raise ValueError("'primitives' must be a non-empty array")
    clean: list[dict[str, Any]] = []
    for i, p in enumerate(prims):
        if not isinstance(p, dict):
            raise ValueError(f"primitive #{i} not an object")
        kind = p.get("kind")
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"primitive #{i} kind={kind!r} not in {ALLOWED_KINDS}")
        if kind == "box":
            for ax in ("x", "y", "z"):
                v = p.get(ax)
                if not (isinstance(v, list) and len(v) == 2
                        and all(isinstance(c, (int, float)) for c in v)):
                    raise ValueError(f"box #{i} axis {ax!r} must be [lo, hi]")
        else:  # line
            pts = p.get("points")
            if not (isinstance(pts, list) and len(pts) >= 2 and all(
                    isinstance(q, list) and len(q) == 3
                    and all(isinstance(c, (int, float)) for c in q)
                    for q in pts)):
                raise ValueError(f"line #{i} 'points' must be array of [x,y,z]")
        clean.append(p)
    return {
        "primitives": clean,
        "title": str(data.get("title", "")),
        "axes": data.get("axes") or {"x": "x (m)", "y": "y (m)", "z": "z (m)"},
    }


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


def _llm_geometry(spec: dict[str, Any]) -> dict[str, Any]:
    """Call the Visualiser LLM. Raises on parse / validation failure."""
    prompt = render("visualiser", spec_json=json.dumps(spec, default=str, indent=2))
    text = chat(prompt, role="visualiser")
    data = json.loads(_strip_code_fences(text))
    return _validate_geometry(data)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def build_geometry(run_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Produce a geometry artifact for ``spec`` and persist it.

    Routing:
      - mock mode  -> deterministic ``_bridge_primitives``.
      - real mode  -> LLM Visualiser; on any failure, fall back to
                      deterministic and log a warning.
    """
    source: str
    is_bridge = _spec_looks_like_bridge(spec)
    if settings.use_mock_llm or not is_bridge:
        # Deterministic recipes produce far more legible non-bridge
        # geometry (curved rollercoaster rails, stacked floors, etc.)
        # than free-form LLM box-piles. Only let the LLM draw bridges.
        geometry = _deterministic_primitives(spec)
        source = "deterministic"
    else:
        try:
            geometry = _llm_geometry(spec)
            # Sanity check: bridges need at minimum a deck + piers + some
            # detail (cables, trusses, arches). Empirically, a credible
            # bridge geometry has > 20 primitives. If the LLM returns a
            # stripped-down box-pile (e.g. "deck + 3 pylons"), fall back
            # to the deterministic recipe so the demo always shows a
            # legible bridge.
            n_prims = len(geometry.get("primitives", []))
            n_lines = sum(1 for p in geometry.get("primitives", [])
                          if p.get("kind") == "line")
            if n_prims < 20 or n_lines == 0:
                log.warning(
                    "visualiser LLM returned sparse geometry "
                    "(%d primitives, %d lines); using deterministic fallback",
                    n_prims, n_lines,
                )
                geometry = _deterministic_primitives(spec)
                source = "deterministic_fallback_sparse"
            else:
                source = "llm"
        except Exception as exc:  # noqa: BLE001 - any LLM failure is recoverable
            log.warning("visualiser LLM failed (%s); using deterministic fallback",
                        exc)
            geometry = _deterministic_primitives(spec)
            source = "deterministic_fallback"
    geometry["source"] = source

    db = get_db()
    insert_with_event(
        "artifacts",
        {
            "run_id": run_id,
            "kind": "geometry_json",
            "uri_or_inline": geometry,
            "created_at": datetime.now(timezone.utc),
        },
        event_kind="geometry_built",
        db=db,
    )
    return geometry
