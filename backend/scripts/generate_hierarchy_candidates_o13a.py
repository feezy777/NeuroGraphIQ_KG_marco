"""O1.3-A: 50-sample hierarchy parent candidate generation + human-readable report.

Stratified deterministic sample of active Function terms → Top-10 candidate
parents each → report written to stdout and data/exports/hierarchy_candidates/.

Usage:
    python scripts/generate_hierarchy_candidates_o13a.py [--top-k 10] [--sample-size 50]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.ontology import (
    OntologyHierarchyCandidate,
    OntologyTerm,
    OntologyTermSynonym,
)
from app.services.function_hierarchy_candidate_service import (
    DEFAULT_TOP_K,
    generate_candidates_batch,
    load_term_index,
)

SEED = 20260821


async def sample_active_terms(session, size: int) -> list[OntologyTerm]:
    active = (
        await session.execute(
            select(OntologyTerm).where(
                OntologyTerm.term_type == "function",
                OntologyTerm.status == "active",
            )
        )
    ).scalars().all()
    idx = await load_term_index(session, include_proposed=False)

    def _usage(t):
        return idx.usage_count.get(t.id, 0)

    def _compound(t):
        return bool(t.canonical_term_en and " and " in t.canonical_term_en.lower())

    def _cn_only(t):
        return bool(t.canonical_term_en and not any(ch.isascii() and ch.isalpha() for ch in t.canonical_term_en))

    rng = random.Random(SEED)
    buckets = {
        "high_usage": [t for t in active if _usage(t) >= 200],
        "mid_usage": [t for t in active if 10 <= _usage(t) < 200],
        "low_usage": [t for t in active if 0 < _usage(t) < 10],
        "no_usage": [t for t in active if _usage(t) == 0],
        "compound": [t for t in active if _compound(t)],
        "long_name": [t for t in active if len((t.canonical_term_en or "").split()) >= 5],
        "cn_name": [t for t in active if _cn_only(t)],
        "single_word": [t for t in active if len((t.canonical_term_en or "").split()) == 1],
    }
    syn_term_ids = {
        r.term_id for r in (await session.execute(select(OntologyTermSynonym))).scalars().all()
    }
    buckets["has_synonym"] = [t for t in active if t.id in syn_term_ids]
    buckets["no_synonym"] = [t for t in active if t.id not in syn_term_ids]

    picked: dict[str, OntologyTerm] = {}
    quotas = {
        "high_usage": 6, "mid_usage": 8, "low_usage": 8, "no_usage": 6,
        "compound": 6, "long_name": 4, "cn_name": 3, "single_word": 2,
        "has_synonym": 4, "no_synonym": 3,
    }
    total_quota = sum(quotas.values())
    scale = max(0.2, size / total_quota)
    quotas = {k: max(1, int(v * scale)) for k, v in quotas.items()}
    for bucket, quota in quotas.items():
        pool = [t for t in buckets.get(bucket, []) if str(t.id) not in picked]
        rng.shuffle(pool)
        for t in pool[:quota]:
            picked[str(t.id)] = t

    # top up with random active terms to reach size
    pool = [t for t in active if str(t.id) not in picked]
    rng.shuffle(pool)
    for t in pool:
        if len(picked) >= size:
            break
        picked[str(t.id)] = t

    sample = list(picked.values())
    sample.sort(key=lambda t: t.canonical_term_en or "")
    return sample


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--sample-size", type=int, default=50)
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        sample = await sample_active_terms(session, args.sample_size)
        print(f"sampled {len(sample)} active terms (seed={SEED})")
        term_ids = [t.id for t in sample]
        result = await generate_candidates_batch(
            session, term_ids, top_k=args.top_k,
            created_by="o13a_sampling",
        )
        await session.commit()

        print(f"total candidates: {result['total_candidates']}")
        print(f"no-candidate by reason: {result['no_candidate_by_reason']}")

        idx = await load_term_index(session, include_proposed=False)
        lines: list[str] = []
        lines.append("# O1.3-A Hierarchy Candidate Report")
        lines.append(f"seed={SEED} top_k={args.top_k} sample={len(sample)}")
        lines.append(f"total_candidates={result['total_candidates']}")
        lines.append("")
        for entry in result["per_term"]:
            term = idx.terms.get(uuid(entry["term_id"]))
            if term is None:
                continue
            lines.append(f"## {term.canonical_term_en}  (usage={idx.usage_count.get(term.id, 0)})")
            if entry["no_candidate_reason"]:
                lines.append(f"  NO CANDIDATE: {entry['no_candidate_reason']}")
                continue
            cands = (await session.execute(
                select(OntologyHierarchyCandidate).where(
                    OntologyHierarchyCandidate.child_term_id == term.id
                ).order_by(OntologyHierarchyCandidate.candidate_score.desc())
            )).scalars().all()
            for i, c in enumerate(cands[: args.top_k], 1):
                parent = await session.get(OntologyTerm, c.parent_term_id)
                pname = parent.canonical_term_en if parent else "?"
                reasons = c.generation_reasons_json or {}
                lines.append(
                    f"  {i}. {pname:<40} score={float(c.candidate_score or 0):.3f} "
                    f"status={c.parent_status or '?'} method={c.generation_method}"
                )
                if reasons:
                    lines.append(f"     reasons: {json.dumps(reasons, ensure_ascii=False)[:160]}")
            lines.append("")

        report = "\n".join(lines)
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "data", "exports", "hierarchy_candidates")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"o13a_report_{SEED}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"report written to {out_path}")
        print(report[:3000])


def uuid(s: str):
    import uuid as _u

    return _u.UUID(s)



if __name__ == "__main__":
    asyncio.run(main())
