"""Seed loader: skills (from data/skills_seed.json) and synthesised agents.

Per MVP_DESIGN.md amendments §3.13: 20 agents total — 14 with 2 skills,
4 with 3 skills, 2 with 4 skills.

prior_reputation per skill (MVP_DESIGN §3.3 amendment):
    raw(s) = 0.5 * log(1+installs) + 0.5 * log(1+stars)
    prior(s) = (raw(s) - min_raw) / (max_raw - min_raw)   # min-max [0,1]
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.db.client import get_db
from src.llm.openai_client import embed

SKILLS_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "skills_seed.json"

AGENT_SKILL_DISTRIBUTION = (
    [2] * 14 + [3] * 4 + [4] * 2
)  # 20 agents total; sum = 28+12+8 = 48 skill-slots
N_AGENTS = len(AGENT_SKILL_DISTRIBUTION)  # 20

_FIRST = ["Stella", "Marco", "Aria", "Boris", "Yuki", "Elena", "Hugo", "Nina",
          "Diego", "Olga", "Felix", "Maya", "Petra", "Quinn", "Rex", "Sasha",
          "Tomas", "Uma", "Viktor", "Wren"]
_LAST = ["Truss", "Beam", "Span", "Cable", "Pier", "Arch", "Deck", "Pylon",
         "Rivet", "Caisson", "Anchor", "Stay", "Joist", "Lintel", "Strut",
         "Bracket", "Bollard", "Coping", "Bearing", "Camber"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _compute_prior_reputations(skills: list[dict[str, Any]]) -> list[float]:
    raw = [
        0.5 * math.log(1 + s["weekly_installs"]) + 0.5 * math.log(1 + s["github_stars"])
        for s in skills
    ]
    lo, hi = min(raw), max(raw)
    span = hi - lo if hi > lo else 1.0
    return [(r - lo) / span for r in raw]


def load_skills_seed() -> list[dict[str, Any]]:
    with SKILLS_SEED_PATH.open() as f:
        return json.load(f)


def seed_skills(*, drop: bool = False) -> int:
    db = get_db()
    if drop:
        db.skills.delete_many({})

    raw = load_skills_seed()
    priors = _compute_prior_reputations(raw)
    now = _now()
    docs = []
    for s, prior in zip(raw, priors):
        embedding_text = f"{s['name']}. {s['description']} Tags: {', '.join(s['tags'])}."
        docs.append({
            **s,
            "embedding": embed(embedding_text),
            "prior_reputation": prior,
            "created_at": now,
        })
    # Upsert by skill_id.
    for d in docs:
        db.skills.update_one({"skill_id": d["skill_id"]}, {"$set": d}, upsert=True)
    return len(docs)


def seed_agents(*, drop: bool = False) -> int:
    db = get_db()
    if drop:
        db.agents.delete_many({})

    rng = random.Random(settings.seed)
    skills = list(db.skills.find({}, {"skill_id": 1, "prior_reputation": 1, "_id": 0}))
    if not skills:
        raise RuntimeError("seed_agents: skills collection is empty; seed skills first")

    skill_ids = [s["skill_id"] for s in skills]
    prior_by_id = {s["skill_id"]: s["prior_reputation"] for s in skills}
    name_pool = [f"{f} {l}" for f, l in zip(_FIRST, _LAST)]
    rng.shuffle(name_pool)

    now = _now()
    docs = []
    for i, n_skills in enumerate(AGENT_SKILL_DISTRIBUTION):
        chosen = rng.sample(skill_ids, n_skills)
        rep = sum(prior_by_id[sid] for sid in chosen) / n_skills
        docs.append({
            "agent_id": f"agent_{i+1:03d}",
            "name": name_pool[i],
            "skill_ids": chosen,
            "polyvalence": n_skills,
            "base_cost": 1.0,
            "base_latency_s": 12,
            "reputation": rep,
            "runs_participated": 0,
            "runs_succeeded": 0,
            "created_at": now,
            "updated_at": now,
        })
    # Add the synthetic marshal agent (per amendment §3.5).
    docs.append({
        "agent_id": "agent_synthetic_marshal",
        "name": "Synthetic Marshal",
        "skill_ids": [],
        "polyvalence": 0,
        "base_cost": 0.5,
        "base_latency_s": 5,
        "reputation": 0.5,
        "runs_participated": 0,
        "runs_succeeded": 0,
        "created_at": now,
        "updated_at": now,
    })

    for d in docs:
        db.agents.update_one({"agent_id": d["agent_id"]}, {"$set": d}, upsert=True)
    return len(docs)
