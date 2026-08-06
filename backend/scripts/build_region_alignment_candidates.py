"""Generate UBERON alignment candidates for brain regions (semi-auto, human review).

Queries the OLS4 UBERON search API by region name, picks the best match
(exact label / synonym match), and writes:
  - backend/data/region_alignment_candidates.json
  - backend/data/region_alignment_candidates.md

No database writes. Candidates must be human-confirmed before applying.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import httpx
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.candidate import CandidateBrainRegion

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OLS_URLS = [
    "https://www.ebi.ac.uk/ols4/api/search",
    "https://www.ebi.ac.uk/ols/api/search",
]

SYNONYM_VARIANTS = {
    "brain stem": "brainstem",
    "csf": "cerebrospinal fluid",
    "caudate": "caudate nucleus",
    "accumbens": "nucleus accumbens",
    "cerebellar vermal lobules": "cerebellar vermis",
}


def _query_variants(name: str) -> list[str]:
    text = (name or "").strip().lower()
    stripped = re.sub(r"^(left|right)\s+", "", text)
    variants = [text, stripped]
    for key, replacement in SYNONYM_VARIANTS.items():
        if key in stripped:
            variants.append(replacement)
    seen = []
    for v in variants:
        if v and v not in seen:
            seen.append(v)
    return seen


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _score(doc_label: str, query: str) -> float:
    q = _tokens(query)
    d = _tokens(doc_label)
    if not q or not d:
        return 0.0
    return len(q & d) / max(len(q), len(d))


async def _search_uberon(client: httpx.AsyncClient, query: str) -> list[dict]:
    for url in OLS_URLS:
        try:
            resp = await client.get(
                url,
                params={"q": query, "ontology": "uberon", "size": 10},
                timeout=20,
            )
            if resp.status_code != 200:
                continue
            payload = resp.json()
            docs = payload.get("response", {}).get("docs") or payload.get("docs") or []
            return list(docs)
        except (httpx.HTTPError, ValueError):
            continue
    return []


def _best_doc(docs: list[dict], name: str) -> tuple[dict | None, float, str]:
    best = None
    best_score = 0.0
    for doc in docs:
        score = _score(str(doc.get("label") or ""), name)
        if score > best_score:
            best = doc
            best_score = score
    if best is None or best_score < 0.4:
        return None, best_score, "not_found"
    match_type = "exact" if best_score >= 1.0 else ("close" if best_score >= 0.66 else "weak")
    return best, best_score, match_type


async def main(atlas: str, limit: int) -> None:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(CandidateBrainRegion)
                .where(CandidateBrainRegion.source_atlas == atlas)
                .order_by(CandidateBrainRegion.en_name)
                .limit(limit)
            )
        ).scalars().all()

    results = []
    async with httpx.AsyncClient(trust_env=False) as client:
        sem = asyncio.Semaphore(2)

        async def one(row) -> None:
            async with sem:
                name = (row.en_name or row.cn_name or "").strip()
                if not name:
                    return
                best = None
                best_score = 0.0
                best_type = "not_found"
                for variant in _query_variants(name):
                    docs = await _search_uberon(client, variant)
                    doc, score, match_type = _best_doc(docs, variant)
                    if doc is not None and score > best_score:
                        best = doc
                        best_score = score
                        best_type = match_type
                    if best_type == "exact":
                        break
                if best is None:
                    results.append(
                        {
                            "region_id": str(row.id),
                            "en_name": row.en_name,
                            "cn_name": row.cn_name,
                            "uberon_iri": None,
                            "match_type": "not_found",
                            "confidence": 0.0,
                        }
                    )
                    return
                label = str(best.get("label") or "")
                iri = str(best.get("iri") or "")
                match_type = best_type
                confidence = 0.97 if match_type == "exact" else (0.85 if match_type == "close" else 0.6)
                results.append(
                    {
                        "region_id": str(row.id),
                        "en_name": row.en_name,
                        "cn_name": row.cn_name,
                        "uberon_iri": iri,
                        "uberon_label": label,
                        "match_type": match_type,
                        "confidence": confidence,
                    }
                )
                await asyncio.sleep(0.1)

        await asyncio.gather(*(one(row) for row in rows))

    results.sort(key=lambda x: (x["match_type"] != "exact", x["en_name"] or ""))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "atlas": atlas,
        "stats": {
            "total": len(results),
            "exact": sum(1 for r in results if r["match_type"] == "exact"),
            "close": sum(1 for r in results if r["match_type"] == "close"),
            "weak": sum(1 for r in results if r["match_type"] == "weak"),
            "not_found": sum(1 for r in results if r["match_type"] == "not_found"),
        },
        "items": results,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    json_path = os.path.join(DATA_DIR, "region_alignment_candidates.json")
    md_path = os.path.join(DATA_DIR, "region_alignment_candidates.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    lines = [
        f"# UBERON 对齐候选（{atlas}）",
        "",
        f"> 生成时间：{report['generated_at']}（OLS4 名称匹配，需人工确认后应用）",
        "",
        "## 统计",
        "",
        f"- 总数：{report['stats']['total']}；exact {report['stats']['exact']}；close {report['stats']['close']}；weak {report['stats']['weak']}；not_found {report['stats']['not_found']}",
        "",
        "## 候选清单",
        "",
        "| 脑区（EN/CN） | UBERON IRI | 匹配 | 置信度 |",
        "|---|---|---|---|",
    ]
    for item in results:
        lines.append(
            f"| {item['en_name']} / {item['cn_name'] or ''} | "
            f"{item.get('uberon_iri') or '—'} | {item['match_type']} | {item['confidence']} |"
        )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(json.dumps(report["stats"], ensure_ascii=False))
    print(f"written: {json_path}")
    print(f"written: {md_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", default="Macro96")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(main(args.atlas, args.limit))
