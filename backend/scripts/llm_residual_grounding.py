"""LLM residual grounding for ungrounded function terms.

Reads ungrounded distinct terms, asks deepseek-v4-flash to suggest canonical
terms, then updates ontology_term_groundings + business term_id.
Terms suggested with confidence >= 0.9 are grounded; if the canonical is new
it is created as `proposed` (created_by=llm). Low-confidence results stay
ungrounded. Idempotent: skips terms already grounded. Runs 4 concurrent
batches to keep wall-clock time reasonable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.ontology import OntologyTerm
from app.services.llm_providers.factory import get_llm_provider
from app.services.ontology_service import _term_code, normalize_term_key

MODEL = "deepseek-v4-flash"
BATCH_SIZE = 20
CONCURRENCY = 2
MAX_TOKENS = 5000
CONFIDENCE_THRESHOLD = 0.9
LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
    "llm_residual_grounding_report.json",
)

TARGET_COLUMNS = {
    "projection_function": ("mirror_projection_functions", "function_term"),
    "circuit_function": ("mirror_circuit_functions", "function_term_en"),
    "region_function": ("mirror_region_functions", "function_term"),
}

term_lock = asyncio.Lock()


async def load_ungrounded_terms() -> dict[str, list[tuple[str, int]]]:
    per_type: dict[str, list[tuple[str, int]]] = {}
    async with AsyncSessionLocal() as session:
        for target_type, (table, column) in TARGET_COLUMNS.items():
            sql = text(
                f"""
                SELECT lower(trim(t.{column})) AS term_key, COUNT(*) AS cnt
                FROM {table} t
                JOIN ontology_term_groundings g
                  ON g.target_type = :tt AND g.target_id = t.id AND g.grounded_by = 'ungrounded'
                WHERE t.{column} IS NOT NULL AND trim(t.{column}) <> ''
                GROUP BY 1
                ORDER BY cnt DESC
                """
            )
            rows = (await session.execute(sql, {"tt": target_type})).all()
            per_type[target_type] = [(r[0], r[1]) for r in rows]
    return per_type


async def load_registry_index() -> tuple[dict[str, int], dict[str, int], set[str]]:
    async with AsyncSessionLocal() as session:
        terms = (await session.execute(select(OntologyTerm))).scalars().all()
    active: dict[str, int] = {}
    proposed: dict[str, int] = {}
    codes = set()
    for term in terms:
        codes.add(term.term_code)
        key = normalize_term_key(term.canonical_term_en)
        if term.status == "active" and key:
            active.setdefault(key, term.id)
        elif term.status == "proposed" and key:
            proposed.setdefault(key, term.id)
    return active, proposed, codes


def _build_prompt(batch: list[tuple[str, int]]) -> tuple[str, str]:
    system = "You are a strict JSON API. Reply only with the requested JSON object. Never explain."
    terms = [term for term, _count in batch]
    user = (
        'Normalize each neuroscience function phrase into a concise lowercase canonical term. '
        'Return JSON exactly like: '
        '{"items": [{"term": "<input>", "canonical_term": "<canonical>", "confidence": 0.95}]}. '
        f"Input terms: {json.dumps(terms, ensure_ascii=False)}"
    )
    return system, user


def _normalize_items(parsed) -> list[dict]:
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        if isinstance(parsed.get("_array"), list):
            items = parsed["_array"]
        elif isinstance(parsed.get("items"), list):
            items = parsed["items"]
        elif parsed:
            pairs = list(parsed.items())
            if pairs and all(isinstance(v, dict) for _, v in pairs):
                # Mapping like {"working memory": {"canonical_term": ..., "confidence": ...}}
                items = []
                for key, val in pairs:
                    val = dict(val)
                    val.setdefault("term", key)
                    items.append(val)
            else:
                # Single object response (first element unwrapped by provider).
                items = [parsed]
        else:
            items = []
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def _parse_results(raw_text: str) -> list[dict]:
    text = (raw_text or "").strip()
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    parsed = json.loads(text)
    items = _normalize_items(parsed)
    if not items:
        raise ValueError("unexpected JSON shape")
    return items


async def _new_proposed_term(
    session,
    canonical: str,
    codes: set[str],
) -> OntologyTerm:
    code = _term_code(canonical, "function")
    if code in codes:
        suffix = 2
        while f"{code}_{suffix}" in codes:
            suffix += 1
        code = f"{code}_{suffix}"
    codes.add(code)
    term = OntologyTerm(
        term_code=code,
        canonical_term_en=canonical,
        status="proposed",
        created_by="llm",
    )
    session.add(term)
    await session.flush()
    return term


async def apply_mapping(
    target_type: str,
    term_key: str,
    term_id,
    confidence: float,
) -> None:
    table, column = TARGET_COLUMNS[target_type]
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                f"UPDATE {table} SET term_id = :tid "
                f"WHERE lower(trim({column})) = :key AND term_id IS NULL"
            ),
            {"tid": term_id, "key": term_key},
        )
        await session.execute(
            text(
                f"""
                UPDATE ontology_term_groundings g
                SET term_id = :tid, grounded_by = 'llm', confidence = :conf
                FROM {table} t
                WHERE g.target_type = :tt
                  AND g.target_id = t.id
                  AND lower(trim(t.{column})) = :key
                  AND t.term_id = :tid
                """
            ),
            {"tid": term_id, "key": term_key, "tt": target_type, "conf": confidence},
        )
        await session.commit()


async def process_batch(
    target_type: str,
    batch: list[tuple[str, int]],
    active_index: dict[str, int],
    proposed_index: dict[str, int],
    codes: set[str],
    stats: Counter,
    report_rows: list[dict],
    provider,
) -> None:
    system_prompt, user_prompt = _build_prompt(batch)
    parsed = None
    for attempt in range(2):
        try:
            prompt = user_prompt
            if attempt == 1:
                prompt = user_prompt + (
                    "\n\nIMPORTANT: Respond with ONLY the raw JSON object. "
                    "No reasoning or text outside JSON."
                )
            text_result = await provider.complete_text(
                model=MODEL,
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=0.1 + 0.1 * attempt,
                max_tokens=MAX_TOKENS,
                json_mode=False,
            )
            parsed = _parse_results(text_result.raw_text or "")
            break
        except Exception as exc:  # noqa: BLE001
            stats["failed"] += 1
            if attempt == 0:
                await asyncio.sleep(20)
                continue
            if attempt == 1:
                detail = ""
                try:
                    if text_result is not None:
                        detail = (
                            f"transport_ok={text_result.transport_ok} "
                            f"err={text_result.error} "
                            f"raw={repr((text_result.raw_text or '')[:200])}"
                        )
                except Exception:  # noqa: BLE001
                    detail = ""
                print(f"[{target_type}] batch failed: {exc} {detail}", flush=True)
    if parsed is None:
        for term, _count in batch:
            report_rows.append({"term": term, "target_type": target_type, "result": "failed"})
        return

    for item in parsed:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        canonical = str(item.get("canonical_term") or "").strip().lower()
        try:
            confidence = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if not term:
            continue
        stats["processed_terms"] += 1
        if confidence < CONFIDENCE_THRESHOLD or not canonical:
            stats["low_confidence"] += 1
            report_rows.append(
                {
                    "term": term,
                    "canonical": canonical,
                    "confidence": confidence,
                    "target_type": target_type,
                    "result": "low_confidence",
                }
            )
            continue
        key = normalize_term_key(canonical)
        if key in active_index:
            term_id = active_index[key]
            method = "active"
        elif key in proposed_index:
            term_id = proposed_index[key]
            method = "proposed"
        else:
            async with term_lock:
                if key in proposed_index:
                    term_id = proposed_index[key]
                    method = "proposed"
                else:
                    async with AsyncSessionLocal() as session:
                        new_term = await _new_proposed_term(session, canonical, codes)
                        await session.commit()
                    term_id = new_term.id
                    proposed_index[key] = term_id
                    stats["created_proposed"] += 1
                    method = "created_proposed"
        await apply_mapping(target_type, term, term_id, confidence)
        if method == "active":
            stats["grounded_active"] += 1
        else:
            stats["grounded_proposed"] += 1
        report_rows.append(
            {
                "term": term,
                "canonical": canonical,
                "confidence": confidence,
                "target_type": target_type,
                "result": method,
            }
        )
    print(
        f"[{target_type}] batch of {len(batch)} done "
        f"(total processed={stats['processed_terms']})",
        flush=True,
    )


async def main(min_count: int) -> None:
    provider = get_llm_provider("deepseek")
    ungrounded = await load_ungrounded_terms()
    active_index, proposed_index, codes = await load_registry_index()

    stats: Counter = Counter({
        "processed_terms": 0,
        "grounded_active": 0,
        "grounded_proposed": 0,
        "created_proposed": 0,
        "low_confidence": 0,
        "failed": 0,
    })
    report_rows: list[dict] = []

    batches: list[tuple[str, list[tuple[str, int]]]] = []
    for target_type, terms in ungrounded.items():
        filtered = [(term, count) for term, count in terms if count >= min_count]
        for start in range(0, len(filtered), BATCH_SIZE):
            batches.append((target_type, filtered[start : start + BATCH_SIZE]))

    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def worker(batch_item: tuple[str, list[tuple[str, int]]]) -> None:
        async with semaphore:
            await process_batch(
                batch_item[0],
                batch_item[1],
                active_index,
                proposed_index,
                codes,
                stats,
                report_rows,
                provider,
            )

    await asyncio.gather(*(worker(batch) for batch in batches))

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "rows": report_rows}, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False))
    print(f"report: {LOG_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-count", type=int, default=2)
    args = parser.parse_args()
    asyncio.run(main(args.min_count))
