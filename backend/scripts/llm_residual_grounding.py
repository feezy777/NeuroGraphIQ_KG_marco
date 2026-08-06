"""LLM residual grounding for ungrounded function terms (structured output).

Reuses the project DeepSeek provider and runtime config; reads model,
concurrency, backoff, batch size, max tokens and confidence threshold from
settings. Responses are validated with Pydantic closed-set schemas. JSON mode
is attempted first; a single retry (plain text + strict parse) is allowed.
Per-batch metadata (model, prompt_version, raw_response, parse_status,
retry_count) is retained in the report. The LLM can only create `proposed`
terms; it never activates, deprecates or merges.
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

from pydantic import ValidationError
from sqlalchemy import select, text

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.ontology import OntologyTerm
from app.services.llm_providers.factory import get_llm_provider
from app.services.ontology_residual_schemas import (
    ResidualBatchOutput,
    ResidualBatchRecord,
    ResidualItemResult,
    ResidualTermItem,
)
from app.services.ontology_service import _term_code, normalize_term_key

PROMPT_VERSION = "residual_alignment_v2"
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


def _settings():
    return get_settings()


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
                  AND g.created_by NOT LIKE 'skipped:%'
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


def _parse_with_fallback(raw_text: str) -> ResidualBatchOutput:
    """Strict parse: try direct json.loads, then fenced/embedded JSON."""
    text_value = (raw_text or "").strip()
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", text_value, re.DOTALL)
    if fence:
        text_value = fence.group(1).strip()
    parsed = json.loads(text_value)
    if isinstance(parsed, list):
        parsed = {"items": parsed}
    return ResidualBatchOutput.model_validate(parsed)


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
    records: list[ResidualBatchRecord],
    provider,
) -> None:
    cfg = _settings()
    model = cfg.ontology_residual_model
    threshold = cfg.ontology_residual_confidence_threshold
    system_prompt, user_prompt = _build_prompt(batch)
    parsed: ResidualBatchOutput | None = None
    parse_status = "provider_error"
    retry_count = 0
    raw_response = ""

    for attempt in range(2):
        retry_count = attempt
        try:
            if attempt == 0:
                response = await provider.complete_json(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.1,
                    max_tokens=cfg.ontology_residual_max_tokens,
                )
                raw_response = response.raw_text or ""
                if response.parsed_json is not None:
                    parsed = ResidualBatchOutput.model_validate(response.parsed_json)
                else:
                    parsed = _parse_with_fallback(raw_response)
            else:
                retry_user = user_prompt + (
                    "\n\nIMPORTANT: Respond with ONLY the raw JSON object. "
                    "No reasoning or text outside JSON."
                )
                text_result = await provider.complete_text(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=retry_user,
                    temperature=0.2,
                    max_tokens=cfg.ontology_residual_max_tokens,
                    json_mode=False,
                )
                raw_response = text_result.raw_text or ""
                parsed = _parse_with_fallback(raw_response)
            parse_status = "ok"
            break
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:  # noqa: BLE001
            parse_status = "schema_error" if isinstance(exc, ValidationError) else "parse_error"
            if attempt == 0:
                await asyncio.sleep(cfg.ontology_residual_backoff_seconds)
                continue
            print(f"[{target_type}] batch failed: {exc}", flush=True)

    item_results: list[ResidualItemResult] = []
    if parsed is not None:
        async with AsyncSessionLocal() as session:
            for item in parsed.items:
                try:
                    validated = ResidualTermItem.model_validate(item.model_dump())
                except ValidationError:
                    stats["invalid"] += 1
                    item_results.append(
                        ResidualItemResult(
                            term=str(item.term), canonical_term="", confidence=0.0,
                            status="invalid", detail="schema validation failed",
                        )
                    )
                    continue
                stats["processed_terms"] += 1
                if validated.confidence < threshold:
                    stats["low_confidence"] += 1
                    item_results.append(
                        ResidualItemResult(
                            term=validated.term,
                            canonical_term=validated.canonical_term,
                            confidence=validated.confidence,
                            status="low_confidence",
                        )
                    )
                    continue
                key = normalize_term_key(validated.canonical_term)
                if key in active_index:
                    term_id = active_index[key]
                    status = "mapped_active"
                elif key in proposed_index:
                    term_id = proposed_index[key]
                    status = "mapped_proposed"
                else:
                    async with term_lock:
                        if key in proposed_index:
                            term_id = proposed_index[key]
                            status = "mapped_proposed"
                        else:
                            new_term = await _new_proposed_term(session, validated.canonical_term, codes)
                            term_id = new_term.id
                            proposed_index[key] = term_id
                            stats["created_proposed"] += 1
                            status = "created_proposed"
                await session.commit()
                await apply_mapping(target_type, validated.term, term_id, validated.confidence)
                stats[status] += 1
                item_results.append(
                    ResidualItemResult(
                        term=validated.term,
                        canonical_term=validated.canonical_term,
                        confidence=validated.confidence,
                        status=status,
                    )
                )
    records.append(
        ResidualBatchRecord(
            target_type=target_type,
            model=model,
            prompt_version=PROMPT_VERSION,
            raw_response=raw_response[:2000],
            parse_status=parse_status,
            retry_count=retry_count,
            items=item_results,
        )
    )
    print(
        f"[{target_type}] batch of {len(batch)} done "
        f"(total processed={stats['processed_terms']}) parse={parse_status}",
        flush=True,
    )


async def main(min_count: int) -> None:
    cfg = _settings()
    provider = get_llm_provider("deepseek")
    ungrounded = await load_ungrounded_terms()
    active_index, proposed_index, codes = await load_registry_index()

    stats: Counter = Counter({
        "processed_terms": 0,
        "mapped_active": 0,
        "mapped_proposed": 0,
        "created_proposed": 0,
        "low_confidence": 0,
        "invalid": 0,
        "failed": 0,
    })
    records: list[ResidualBatchRecord] = []

    batches: list[tuple[str, list[tuple[str, int]]]] = []
    for target_type, terms in ungrounded.items():
        filtered = [(term, count) for term, count in terms if count >= min_count]
        for start in range(0, len(filtered), cfg.ontology_residual_batch_size):
            batches.append((target_type, filtered[start : start + cfg.ontology_residual_batch_size]))

    semaphore = asyncio.Semaphore(cfg.ontology_residual_concurrency)

    async def worker(batch_item: tuple[str, list[tuple[str, int]]]) -> None:
        async with semaphore:
            await process_batch(
                batch_item[0],
                batch_item[1],
                active_index,
                proposed_index,
                codes,
                stats,
                records,
                provider,
            )

    await asyncio.gather(*(worker(batch) for batch in batches))

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "stats": dict(stats),
                "records": [record.model_dump(mode="json") for record in records],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(json.dumps(dict(stats), ensure_ascii=False))
    print(f"report: {LOG_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-count", type=int, default=2)
    args = parser.parse_args()
    asyncio.run(main(args.min_count))
