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

from src.config import settings
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

    # Deck
    prims.append(_box(0.0, L, -W / 2, W / 2,
                      z_deck, z_deck + deck_t,
                      "#2c2c2c", "deck"))

    # Piers
    xs = _support_xs(spec) or [0.0, L]
    for xp in xs:
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
        "extent": {"x": [0.0, L], "y": [-W, W], "z": [-1.0, z_deck * 5]},
    }
    return geometry


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
    if settings.use_mock_llm:
        geometry = _bridge_primitives(spec)
        source = "deterministic"
    else:
        try:
            geometry = _llm_geometry(spec)
            source = "llm"
        except Exception as exc:  # noqa: BLE001 - any LLM failure is recoverable
            log.warning("visualiser LLM failed (%s); using deterministic fallback",
                        exc)
            geometry = _bridge_primitives(spec)
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
