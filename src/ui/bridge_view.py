"""Stylised bridge elevation renderer for the Streamlit Bridge tab.

Renders a side-elevation that adapts to the design typology:
  * cable_stayed   — pylons with fanned stay cables to the deck
  * suspension     — twin towers with a parabolic main cable + verticals
  * arch           — single arch beneath the deck
  * truss / beam / default — multi-span girder on piers

Aesthetic touches: sky gradient, water with mirrored reflection of the
structure, soft shadow under the deck. The figure is purely indicative —
proportions are exaggerated for legibility (vertical exaggeration ~3-4×).
"""
from __future__ import annotations
from typing import Any

import numpy as np
import plotly.graph_objects as go


SKY_TOP = "#cfe6ff"
SKY_BOTTOM = "#fef6e4"
WATER_TOP = "rgba(80,140,200,0.55)"
WATER_BOTTOM = "rgba(20,50,90,0.85)"
DECK_COLOR = "#2c2c2c"
PIER_COLOR = "#7a7a7a"
PYLON_COLOR = "#d35400"
CABLE_COLOR = "rgba(40,40,40,0.65)"
ARCH_COLOR = "#a85a3c"
SHADOW_COLOR = "rgba(0,0,0,0.18)"


def _support_xs(layout: list[dict]) -> list[float]:
    xs = [0.0]
    x = 0.0
    for s in layout:
        x += s.get("length_m", 0)
        xs.append(x)
    return xs


def _classify(spec: dict) -> str:
    btype = (spec.get("bridge_type") or "").lower()
    if "cable" in btype and "stay" in btype:
        return "cable_stayed"
    if "suspension" in btype:
        return "suspension"
    if "arch" in btype:
        return "arch"
    if "truss" in btype:
        return "truss"
    return "girder"


def _add_sky_and_water(fig: go.Figure, x0: float, x1: float,
                       y_water_bottom: float, y_sky_top: float) -> None:
    # Sky band (above deck)
    fig.add_shape(
        type="rect", x0=x0, x1=x1, y0=0, y1=y_sky_top,
        fillcolor=SKY_TOP, line_width=0, layer="below",
    )
    # Water with vertical gradient via stacked thin rects
    n = 18
    for i in range(n):
        t = i / (n - 1)
        # interp top → bottom
        fig.add_shape(
            type="rect",
            x0=x0, x1=x1,
            y0=y_water_bottom + (1 - (i + 1) / n) * (-y_water_bottom),
            y1=y_water_bottom + (1 - i / n) * (-y_water_bottom),
            fillcolor=WATER_TOP if t < 0.4 else WATER_BOTTOM,
            line_width=0, layer="below", opacity=0.55 + 0.4 * t,
        )
    # Water surface line
    fig.add_shape(
        type="line", x0=x0, x1=x1, y0=0, y1=0,
        line=dict(color="rgba(255,255,255,0.55)", width=1),
        layer="below",
    )


def _add_deck(fig: go.Figure, x0: float, x1: float, y_deck: float,
              deck_thickness: float) -> None:
    # Deck shadow on water
    fig.add_shape(
        type="rect",
        x0=x0, x1=x1, y0=-deck_thickness * 0.4, y1=0,
        fillcolor=SHADOW_COLOR, line_width=0, layer="below",
    )
    # Deck slab as a filled rect
    fig.add_shape(
        type="rect",
        x0=x0, x1=x1,
        y0=y_deck, y1=y_deck + deck_thickness,
        fillcolor=DECK_COLOR, line_width=0, layer="above",
    )
    # Mirrored reflection of deck on water
    fig.add_shape(
        type="rect",
        x0=x0, x1=x1,
        y0=-(y_deck + deck_thickness) * 0.35,
        y1=-y_deck * 0.35,
        fillcolor="rgba(44,44,44,0.18)", line_width=0, layer="below",
    )


def _add_piers(fig: go.Figure, xs: list[float], y_deck: float,
               pier_width: float, total_length: float) -> None:
    """Add piers to the bridge figure, including reflections.

    Args:
        fig (go.Figure): Plotly figure to add shapes to.
        xs (list[float]): X positions of supports/piers.
        y_deck (float): Y position of the deck.
        pier_width (float): Width of each pier.
        total_length (float): Total bridge length.
    """
    for xp in xs:
        # taper piers slightly (top narrower)
        top_half = pier_width * 0.4
        bot_half = pier_width * 0.7
        path = (
            f"M {xp - top_half},{y_deck} "
            f"L {xp + top_half},{y_deck} "
            f"L {xp + bot_half},0 "
            f"L {xp - bot_half},0 Z"
        )
        fig.add_shape(type="path", path=path,
                      fillcolor=PIER_COLOR, line=dict(color="#555", width=1),
                      layer="above")
        # reflection
        path_ref = (
            f"M {xp - top_half},{-y_deck * 0.35} "
            f"L {xp + top_half},{-y_deck * 0.35} "
            f"L {xp + bot_half},0 "
            f"L {xp - bot_half},0 Z"
        )
        fig.add_shape(type="path", path=path_ref,
                      fillcolor="rgba(122,122,122,0.18)",
                      line_width=0, layer="below")


def _add_cable_stayed(fig: go.Figure, xs: list[float], y_deck: float,
                      total_length: float) -> tuple[float, float]:
    """Add cable-stayed pylons and cables to the figure.

    Args:
        fig (go.Figure): Plotly figure to add shapes to.
        xs (list[float]): X positions of supports/piers.
        y_deck (float): Y position of the deck.
        total_length (float): Total bridge length.

    Returns:
        tuple[float, float]: (y position of pylon top, pylon height)
    """
    n_supports = len(xs)
    if n_supports < 3:
        return y_deck, y_deck
    # pylons on internal piers, every other one (so cables don't overlap)
    pylon_idxs = list(range(1, n_supports - 1, 2))
    if not pylon_idxs:
        pylon_idxs = [n_supports // 2]
    pylon_height = max(total_length * 0.05, y_deck * 1.6)

    for i in pylon_idxs:
        xp = xs[i]
        # tower
        fig.add_shape(
            type="line", x0=xp, x1=xp, y0=y_deck, y1=y_deck + pylon_height,
            line=dict(color=PYLON_COLOR, width=6),
            layer="above",
        )
        # tower cap
        fig.add_shape(
            type="circle",
            x0=xp - total_length * 0.005, x1=xp + total_length * 0.005,
            y0=y_deck + pylon_height - total_length * 0.005,
            y1=y_deck + pylon_height + total_length * 0.005,
            fillcolor=PYLON_COLOR, line_width=0,
        )
        # fanned stay cables (back & forward)
        span_back = xp - xs[i - 1] if i > 0 else total_length / n_supports
        span_fwd = xs[i + 1] - xp if i + 1 < n_supports else total_length / n_supports
        n_cables = 6
        for k in range(1, n_cables + 1):
            frac = k / (n_cables + 1)
            x_back = xp - frac * span_back
            x_fwd = xp + frac * span_fwd
            fig.add_shape(
                type="line", x0=xp, y0=y_deck + pylon_height,
                x1=x_back, y1=y_deck,
                line=dict(color=CABLE_COLOR, width=1.2),
                layer="above",
            )
            fig.add_shape(
                type="line", x0=xp, y0=y_deck + pylon_height,
                x1=x_fwd, y1=y_deck,
                line=dict(color=CABLE_COLOR, width=1.2),
                layer="above",
            )
        # pylon reflection
        fig.add_shape(
            type="line", x0=xp, x1=xp,
            y0=-y_deck * 0.35, y1=-(y_deck + pylon_height) * 0.20,
            line=dict(color="rgba(211,84,0,0.25)", width=4),
            layer="below",
        )
    return y_deck + pylon_height, pylon_height


def _add_suspension(fig: go.Figure, xs: list[float], y_deck: float,
                    total_length: float) -> float:
    """Add suspension towers, main cable, and hangers to the figure.

    Args:
        fig (go.Figure): Plotly figure to add shapes to.
        xs (list[float]): X positions of supports/piers.
        y_deck (float): Y position of the deck.
        total_length (float): Total bridge length.

    Returns:
        float: Y position of the main cable top.
    """
    if len(xs) < 2:
        return y_deck
    # Two towers at ~25% and ~75% of length.
    xL = xs[0] + 0.25 * (xs[-1] - xs[0])
    xR = xs[0] + 0.75 * (xs[-1] - xs[0])
    tower_h = max(total_length * 0.06, y_deck * 1.8)
    top = y_deck + tower_h
    for xt in (xL, xR):
        fig.add_shape(type="line", x0=xt, x1=xt, y0=y_deck, y1=top,
                      line=dict(color=PYLON_COLOR, width=6), layer="above")
    # Parabolic main cable in three segments
    def parabola(x_a: float, y_a: float, x_b: float, y_b: float,
                 sag: float, n: int = 40):
        """Generate a parabolic curve between two points with sag.

        Args:
            x_a (float): Start x.
            y_a (float): Start y.
            x_b (float): End x.
            y_b (float): End y.
            sag (float): Sag depth below straight line.
            n (int): Number of points.

        Returns:
            tuple[np.ndarray, np.ndarray]: X and Y coordinates of the parabola.
        """
        xs_seg = np.linspace(x_a, x_b, n)
        # quadratic dipping by 'sag' below straight line
        ys_seg = np.linspace(y_a, y_b, n)
        u = (xs_seg - x_a) / max(x_b - x_a, 1e-9)
        ys_seg = ys_seg - sag * (4 * u * (1 - u))
        return xs_seg, ys_seg

    sag_main = (xR - xL) * 0.18
    for x_a, y_a, x_b, y_b, sag in [
        (xs[0], y_deck, xL, top, 0.0),
        (xL, top, xR, top, sag_main),
        (xR, top, xs[-1], y_deck, 0.0),
    ]:
        xx, yy = parabola(x_a, y_a, x_b, y_b, sag)
        fig.add_trace(go.Scatter(x=xx, y=yy, mode="lines",
                                 line=dict(color=CABLE_COLOR, width=2.5),
                                 hoverinfo="skip", showlegend=False))
        # vertical hangers
        for k in range(2, len(xx) - 1, 3):
            fig.add_shape(type="line", x0=xx[k], x1=xx[k],
                          y0=y_deck, y1=yy[k],
                          line=dict(color=CABLE_COLOR, width=0.8),
                          layer="above")
    return top


def _add_arch(fig: go.Figure, xs: list[float], y_deck: float,
              total_length: float) -> float:
    """Add an arch and spandrel verticals to the figure.

    Args:
        fig (go.Figure): Plotly figure to add shapes to.
        xs (list[float]): X positions of supports/piers.
        y_deck (float): Y position of the deck.
        total_length (float): Total bridge length.

    Returns:
        float: Y position of the arch crown.
    """
    if len(xs) < 2:
        return y_deck
    x0, x1 = xs[0], xs[-1]
    rise = (x1 - x0) * 0.18
    n = 80
    xx = np.linspace(x0, x1, n)
    u = (xx - x0) / (x1 - x0)
    yy = y_deck * 0.1 + rise * (4 * u * (1 - u))
    fig.add_trace(go.Scatter(
        x=xx, y=yy, mode="lines",
        line=dict(color=ARCH_COLOR, width=8), hoverinfo="skip",
        showlegend=False,
    ))
    # spandrel verticals
    for k in range(8, n - 8, 6):
        fig.add_shape(type="line", x0=xx[k], x1=xx[k],
                      y0=yy[k], y1=y_deck,
                      line=dict(color=ARCH_COLOR, width=2),
                      layer="above")
    return y_deck + rise


def _add_truss(fig: go.Figure, xs: list[float], y_deck: float,
               deck_thickness: float) -> float:
    """Add a truss structure above the deck to the figure.

    Args:
        fig (go.Figure): Plotly figure to add shapes to.
        xs (list[float]): X positions of supports/piers.
        y_deck (float): Y position of the deck.
        deck_thickness (float): Thickness of the deck.

    Returns:
        float: Y position of the truss top.
    """
    truss_h = max(deck_thickness * 4, 6)
    top_y = y_deck + deck_thickness + truss_h
    for i in range(len(xs) - 1):
        x_a, x_b = xs[i], xs[i + 1]
        y_b = y_deck + deck_thickness
        # top chord
        fig.add_shape(type="line", x0=x_a, x1=x_b, y0=top_y, y1=top_y,
                      line=dict(color="#555", width=3), layer="above")
        # diagonals (zig-zag)
        n_panels = 6
        for k in range(n_panels):
            xa = x_a + (x_b - x_a) * (k / n_panels)
            xc = x_a + (x_b - x_a) * ((k + 1) / n_panels)
            ya, yc = (y_b, top_y) if k % 2 == 0 else (top_y, y_b)
            fig.add_shape(type="line", x0=xa, x1=xc, y0=ya, y1=yc,
                          line=dict(color="#555", width=1.5), layer="above")
        # verticals at panel points
        for k in range(0, n_panels + 1):
            xa = x_a + (x_b - x_a) * (k / n_panels)
            fig.add_shape(type="line", x0=xa, x1=xa, y0=y_b, y1=top_y,
                          line=dict(color="#555", width=1), layer="above")
    return top_y


def render_bridge(spec: dict[str, Any]) -> go.Figure:
    """Render a stylised side-elevation Plotly figure for a bridge ``spec``.

    Adapts to ``spec['bridge_type']`` (cable-stayed, suspension, arch,
    truss, or default girder). Proportions are exaggerated for legibility;
    the figure is illustrative, not to scale.
    """
    layout = spec.get("span_layout") or []
    L = spec.get("total_length_m") or sum(s.get("length_m", 0) for s in layout) or 1
    longest = max((s.get("length_m", 0) for s in layout), default=L)
    # Vertical exaggeration helps legibility for very long bridges.
    y_deck = max(spec.get("structural_depth_m") or 0, longest / 14.0, L * 0.012)
    deck_thickness = max(longest / 50.0, L * 0.004)
    pier_width = max(L * 0.006, 1.5)
    xs = _support_xs(layout) if layout else [0.0, L]

    fig = go.Figure()
    # Background sky + water
    sky_top_provisional = max(y_deck * 4, L * 0.10)
    _add_sky_and_water(fig, 0, L, y_water_bottom=-y_deck * 0.55,
                       y_sky_top=sky_top_provisional)

    # Per-typology superstructure
    typology = _classify(spec)
    extra_top = y_deck
    if typology == "cable_stayed":
        extra_top, _ = _add_cable_stayed(fig, xs, y_deck, L)
    elif typology == "suspension":
        extra_top = _add_suspension(fig, xs, y_deck, L)
    elif typology == "arch":
        extra_top = _add_arch(fig, xs, y_deck, L)
    elif typology == "truss":
        extra_top = _add_truss(fig, xs, y_deck, deck_thickness)

    _add_deck(fig, 0, L, y_deck, deck_thickness)
    _add_piers(fig, xs, y_deck, pier_width, L)

    # Lay sky band right up to whatever superstructure is tallest
    sky_top = max(sky_top_provisional, extra_top * 1.15)

    # Title annotation
    title = (
        f"<b>{spec.get('bridge_type', 'bridge').replace('_', ' ').title()}</b>  ·  "
        f"{int(L)} m total  ·  longest span {int(longest)} m  ·  "
        f"{spec.get('primary_material', '').replace('_', ' ')}"
    )
    fig.update_layout(
        height=460,
        title=dict(text=title, x=0.02, y=0.96, font=dict(size=14)),
        xaxis=dict(
            title="Distance along bridge (m)", range=[-L * 0.02, L * 1.02],
            showgrid=False, zeroline=False,
        ),
        yaxis=dict(
            title="", range=[-y_deck * 0.7, sky_top],
            showgrid=False, zeroline=False, showticklabels=False,
            scaleanchor="x", scaleratio=1.0,
        ),
        margin=dict(l=20, r=20, t=40, b=40),
        plot_bgcolor=SKY_BOTTOM,
        paper_bgcolor=SKY_BOTTOM,
        showlegend=False,
    )
    return fig
