"""Tests for the AI hero-render stage and the llm_cache collection.

Both features are nice-to-have polish; they must not regress when
``USE_MOCK_LLM=true`` (the default test env).
"""
from __future__ import annotations

from src.core.config import settings
from src.db.client import COLLECTIONS, get_db
from src.pipeline import concept_render
from src.pipeline.orchestrator import run_pipeline


def test_llm_cache_collection_registered():
    """Test that `llm_cache` is registered in COLLECTIONS and created by ensure_collections."""
    """`llm_cache` must be in COLLECTIONS so ensure_collections creates it."""
    assert "llm_cache" in COLLECTIONS


def test_concept_render_mock_mode_produces_placeholder():
    """Test that concept render in mock mode produces a placeholder SVG artifact and is idempotent."""
    assert settings.use_mock_llm, "test requires mock mode"
    out = run_pipeline("design a 1 km cable-stayed bridge for 60 cars/h")
    run_id = out["run_id"]
    db = get_db()
    spec = db.design_specs.find_one({"run_id": run_id}, {"_id": 0}) or {}

    art = concept_render.generate(run_id, "design a 1 km bridge", spec)
    assert art["kind"] == concept_render.ARTIFACT_KIND
    payload = art["uri_or_inline"]
    assert payload["data_url"].startswith("data:image/svg+xml;base64,")
    assert payload["placeholder"] is True
    assert art["model"] == "mock"

    # Idempotent: calling again returns the cached artifact, no duplicate row.
    art2 = concept_render.generate(run_id, "design a 1 km bridge", spec)
    assert art2["uri_or_inline"]["data_url"] == payload["data_url"]
    n_rows = db.artifacts.count_documents(
        {"run_id": run_id, "kind": concept_render.ARTIFACT_KIND}
    )
    assert n_rows == 1, n_rows

    # An events row was emitted.
    n_events = db.events.count_documents(
        {"run_id": run_id, "kind": "concept_render_built"}
    )
    assert n_events >= 1


def test_build_image_prompt_is_deterministic_and_visual():
    """Test that build_image_prompt is deterministic and includes key spec details."""
    spec = {
        "domain": "bridge",
        "bridge_type": "cable-stayed",
        "primary_material": "steel",
        "dimensions": {"length_m": 2000, "width_m": 22, "height_m": 80},
        "aesthetic": "modern",
    }
    p1 = concept_render.build_image_prompt("a 2 km bridge", spec)
    p2 = concept_render.build_image_prompt("a 2 km bridge", spec)
    assert p1 == p2  # deterministic
    assert "2000" in p1 and "cable-stayed" in p1 and "steel" in p1
    assert "no text" in p1  # photoreal hint preserved
