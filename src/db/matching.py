"""Stage-1 retrieval: embed a capability string and run Atlas $vectorSearch
against the ``skills`` collection.

Per MVP_DESIGN §4.2: ``numCandidates=100``, ``limit=8``, optional ``$match``
on category. We expose ``search_skills`` for use by the decomposer/matching
pipeline and a thin in-Python cosine fallback used when Atlas Vector Search
is unavailable (development only — G5 still requires Atlas).
"""
from __future__ import annotations

import logging
from typing import Iterable

from pymongo.errors import OperationFailure

from src.db.client import get_db
from src.db.indexes import VECTOR_INDEX_NAME
from src.llm.openai_client import embed

log = logging.getLogger(__name__)


def search_skills(
    query: str,
    *,
    limit: int = 8,
    num_candidates: int = 100,
    categories: Iterable[str] | None = None,
) -> list[dict]:
    """Return top-N skill docs ranked by embedding similarity to *query*."""
    db = get_db()
    qvec = embed(query)
    pipeline: list[dict] = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": qvec,
                "numCandidates": num_candidates,
                "limit": limit,
            }
        }
    ]
    if categories:
        pipeline.append({"$match": {"category": {"$in": list(categories)}}})
    pipeline.append({
        "$project": {
            "_id": 0,
            "skill_id": 1,
            "name": 1,
            "category": 1,
            "tags": 1,
            "prior_reputation": 1,
            "weekly_installs": 1,
            "score": {"$meta": "vectorSearchScore"},
        }
    })
    try:
        return list(db.skills.aggregate(pipeline))
    except OperationFailure as e:
        log.warning(
            "Atlas $vectorSearch failed (%s); falling back to in-Python cosine. "
            "G5 requires Atlas vector search — index may still be building.",
            e,
        )
        return _cosine_fallback(query, qvec, limit, categories)


def _cosine_fallback(
    query: str,
    qvec: list[float],
    limit: int,
    categories: Iterable[str] | None,
) -> list[dict]:
    import numpy as np

    db = get_db()
    filt = {"category": {"$in": list(categories)}} if categories else {}
    rows = list(db.skills.find(
        filt,
        {"_id": 0, "skill_id": 1, "name": 1, "category": 1, "tags": 1,
         "prior_reputation": 1, "weekly_installs": 1, "embedding": 1},
    ))
    if not rows:
        return []
    q = np.asarray(qvec, dtype=np.float32)
    q /= max(float(np.linalg.norm(q)), 1e-12)
    scored = []
    for r in rows:
        e = np.asarray(r.pop("embedding"), dtype=np.float32)
        e /= max(float(np.linalg.norm(e)), 1e-12)
        r["score"] = float(q @ e)
        scored.append(r)
    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored[:limit]
