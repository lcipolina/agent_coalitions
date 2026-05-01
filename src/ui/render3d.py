"""Generic 3D renderer for geometry artifacts.

Domain-agnostic on purpose: it draws whatever primitives it is given.
The mapping from a design spec to primitives is the responsibility of
``src.pipeline.visualiser`` (a separate pipeline stage).

Supported primitives:
  * ``box``  — axis-aligned cuboid via ``go.Mesh3d``.
  * ``line`` — polyline via ``go.Scatter3d`` with ``mode='lines'``.
"""
from __future__ import annotations

from typing import Any

import plotly.graph_objects as go


# Vertices of a unit cube indexed:
#   0:(0,0,0) 1:(1,0,0) 2:(1,1,0) 3:(0,1,0)
#   4:(0,0,1) 5:(1,0,1) 6:(1,1,1) 7:(0,1,1)
# Six faces, two triangles each:
_BOX_I = [0, 0, 4, 4, 0, 0, 3, 3, 0, 0, 1, 1]
_BOX_J = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 2, 6]
_BOX_K = [2, 3, 6, 7, 5, 4, 6, 7, 7, 4, 6, 5]


def _box_trace(p: dict[str, Any]) -> go.Mesh3d:
    x0, x1 = p["x"]
    y0, y1 = p["y"]
    z0, z1 = p["z"]
    xs = [x0, x1, x1, x0, x0, x1, x1, x0]
    ys = [y0, y0, y1, y1, y0, y0, y1, y1]
    zs = [z0, z0, z0, z0, z1, z1, z1, z1]
    return go.Mesh3d(
        x=xs, y=ys, z=zs,
        i=_BOX_I, j=_BOX_J, k=_BOX_K,
        color=p.get("color", "#888"),
        opacity=p.get("opacity", 1.0),
        name=p.get("name", "box"),
        flatshading=True,
        hoverinfo="name",
        showscale=False,
    )


def _line_trace(p: dict[str, Any]) -> go.Scatter3d:
    pts = p["points"]
    return go.Scatter3d(
        x=[q[0] for q in pts],
        y=[q[1] for q in pts],
        z=[q[2] for q in pts],
        mode="lines",
        line=dict(color=p.get("color", "#444"),
                  width=float(p.get("width", 2.0))),
        name=p.get("name", "line"),
        hoverinfo="name",
        showlegend=False,
    )


def render_geometry(geometry: dict[str, Any]) -> go.Figure:
    """Build a Plotly figure from a geometry artifact (boxes + polylines)."""
    fig = go.Figure()
    for prim in geometry.get("primitives", []):
        kind = prim.get("kind")
        if kind == "box":
            fig.add_trace(_box_trace(prim))
        elif kind == "line":
            fig.add_trace(_line_trace(prim))
        # silently ignore unknown kinds — keeps the renderer forward-compatible

    axes = geometry.get("axes", {})
    fig.update_layout(
        title=dict(text=geometry.get("title", ""), x=0.02, y=0.98,
                   font=dict(size=14)),
        scene=dict(
            xaxis=dict(title=axes.get("x", "x"),
                       backgroundcolor="#eef2f5", showbackground=True),
            yaxis=dict(title=axes.get("y", "y"),
                       backgroundcolor="#eef2f5", showbackground=True),
            zaxis=dict(title=axes.get("z", "z"),
                       backgroundcolor="#eef2f5", showbackground=True),
            aspectmode="data",
            camera=dict(eye=dict(x=1.4, y=-1.6, z=0.85)),
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        height=580,
        showlegend=False,
        paper_bgcolor="white",
    )
    return fig
