"""AI hero render \u2014 OpenAI image generation for the Concept render tab.

Optional pipeline step. Unlike the deterministic 3D primitives produced
by :mod:`src.pipeline.visualiser`, this module asks an image model
(default ``gpt-image-1``) to generate a single hero illustration of the
synthesised design. The image is persisted as an ``artifacts`` row of
kind ``concept_render`` so it is replayable.

Triggered on demand from the Streamlit UI rather than from
:func:`src.pipeline.orchestrator.run_pipeline`. Image generation costs
real money per call (~5\u201310 cents on ``gpt-image-1``) and adds 10\u201320 s
of latency, so we keep it out of the default run and let demo audiences
opt in.

In ``USE_MOCK_LLM=true`` mode we never call the API. We return a tiny
deterministic SVG placeholder so the UI still has *something* to draw,
clearly labelled as a placeholder. The same fallback is used if the
real API call fails for any reason \u2014 the demo never crashes here.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from src.core.config import settings
from src.db.writes import insert_with_event
from src.llm import openai_client

log = logging.getLogger(__name__)

ARTIFACT_KIND = "concept_render"
DEFAULT_IMAGE_MODEL = "gpt-image-1"
DEFAULT_SIZE = "1024x1024"


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
def build_image_prompt(prompt: str, spec: dict[str, Any]) -> str:
    """Turn the original brief + synthesised spec into a hero-render prompt.

    Kept short and visual; the image model rejects overly engineering-y
    prompts. We bias toward photoreal architectural visualisation.
    """
    dims = spec.get("dimensions") or {}
    L = dims.get("length_m") or spec.get("total_length_m")
    W = dims.get("width_m") or spec.get("deck_width_m")
    H = dims.get("height_m")
    bridge_type = spec.get("bridge_type") or spec.get("structural_system")
    material = spec.get("primary_material") or spec.get("material")
    style = spec.get("aesthetic") or "modern"
    domain = (spec.get("domain") or spec.get("design_type") or "").strip()

    bits: list[str] = []
    if domain and bridge_type:
        bits.append(f"a {style} {bridge_type} {domain}")
    elif domain:
        bits.append(f"a {style} {domain}")
    elif bridge_type:
        bits.append(f"a {style} {bridge_type} bridge")
    else:
        bits.append(f"a {style} engineered structure")
    if material:
        bits.append(f"primary material: {material}")
    if L:
        bits.append(f"length ~{int(L)} m")
    if W:
        bits.append(f"width ~{int(W)} m")
    if H:
        bits.append(f"height ~{int(H)} m")
    bits.append(f"design brief: {prompt[:160]}")
    bits.append(
        "photoreal architectural visualisation, daylight, eye-level "
        "three-quarter view, no text, no people, neutral background"
    )
    return ". ".join(bits)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def generate(
    run_id: str, prompt: str, spec: dict[str, Any], *,
    model: str = DEFAULT_IMAGE_MODEL, size: str = DEFAULT_SIZE,
) -> dict[str, Any]:
    """Generate (or fetch from cache) the concept render for a run.

    Returns the persisted ``artifacts`` row payload (without ``_id``).
    The artifact's ``uri_or_inline`` carries either:

    * ``{"data_url": "data:image/...;base64,..."}`` for real renders;
    * ``{"data_url": "data:image/svg+xml;utf8,...", "placeholder": True}``
      for mock-mode / fallback renders.

    Idempotent per run: a second call returns the existing artifact.
    """
    # Already generated for this run? Just return it.
    from src.db.client import get_db
    db = get_db()
    existing = db.artifacts.find_one(
        {"run_id": run_id, "kind": ARTIFACT_KIND}, {"_id": 0},
    )
    if existing:
        return existing

    image_prompt = build_image_prompt(prompt, spec)
    payload: dict[str, Any]
    if settings.use_mock_llm:
        payload = _placeholder_svg(image_prompt, reason="mock mode")
    else:
        try:
            payload = _call_image_api(image_prompt, model=model, size=size)
        except Exception as exc:  # noqa: BLE001 \u2014 demo must not crash here
            log.warning("concept render API call failed: %s", exc)
            payload = _placeholder_svg(image_prompt, reason=f"api error: {exc}")

    artifact = {
        "run_id": run_id,
        "kind": ARTIFACT_KIND,
        "uri_or_inline": payload,
        "image_prompt": image_prompt,
        "model": model if not settings.use_mock_llm else "mock",
        "created_at": datetime.now(timezone.utc),
    }
    insert_with_event(
        "artifacts", artifact,
        event_kind="concept_render_built",
        event_payload={
            "model": artifact["model"],
            "placeholder": payload.get("placeholder", False),
        },
    )
    artifact.pop("_id", None)
    return artifact


def _call_image_api(image_prompt: str, *, model: str, size: str) -> dict[str, Any]:
    """Real OpenAI image generation. Returns a base64 data URL payload.

    Bumps the LLM call counter so the G9 replay invariant still holds
    (replay must not enter this code path).
    """
    # Local import keeps the openai dep optional at module-import time.
    from openai import OpenAI

    openai_client._bump()  # noqa: SLF001 \u2014 deliberate: same call-counter semantics
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.images.generate(
        model=model, prompt=image_prompt, size=size, n=1,
    )
    data = resp.data[0]
    if getattr(data, "b64_json", None):
        b64 = data.b64_json
        return {"data_url": f"data:image/png;base64,{b64}"}
    # Fallback: some models / sizes return a URL only.
    if getattr(data, "url", None):
        return {"data_url": data.url, "remote": True}
    raise RuntimeError("image API returned neither b64_json nor url")


def _placeholder_svg(image_prompt: str, *, reason: str) -> dict[str, Any]:
    """Deterministic offline placeholder so mock mode still has a picture.

    Produces a labelled gradient panel keyed on the prompt hash so the
    same spec always yields the same placeholder.
    """
    seed = hashlib.sha256(image_prompt.encode("utf-8")).hexdigest()
    hue1 = int(seed[:2], 16) * 360 // 255
    hue2 = (hue1 + 60) % 360
    label = (image_prompt[:60] + ("\u2026" if len(image_prompt) > 60 else ""))
    label = label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="hsl({hue1},70%,55%)"/>'
        f'<stop offset="100%" stop-color="hsl({hue2},70%,35%)"/>'
        '</linearGradient></defs>'
        '<rect width="1024" height="1024" fill="url(#g)"/>'
        '<rect x="64" y="800" width="896" height="160" rx="16" fill="rgba(0,0,0,0.55)"/>'
        '<text x="96" y="860" fill="white" font-family="-apple-system,Segoe UI,Helvetica,sans-serif" '
        'font-size="34" font-weight="700">Concept render placeholder</text>'
        f'<text x="96" y="910" fill="white" font-family="monospace" font-size="22" opacity="0.85">{label}</text>'
        '<text x="96" y="950" fill="white" font-family="monospace" font-size="18" opacity="0.6">'
        'mock / fallback \u2014 enable USE_MOCK_LLM=false to call the real image API'
        '</text>'
        '</svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return {
        "data_url": f"data:image/svg+xml;base64,{b64}",
        "placeholder": True,
        "reason": reason,
    }
