"""Fill missing Chinese fields across granularities via DeepSeek translation.

Targets:
  - mirror_region_circuits.name_cn      (source: circuit_name)
  - ontology_terms.canonical_term_cn    (source: canonical_term_en, audited)

Reuses the project DeepSeek provider + config; JSON mode first, Pydantic
validation, per-item failure isolation, per-batch metadata retained.

Usage:
  python scripts/fill_missing_chinese.py --scope circuits|terms|all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, text

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.ontology import OntologyChangeLog, OntologyTerm
from app.services.llm_providers.factory import get_llm_provider

PROMPT_VERSION = "zh_translation_v1"


class TranslationItem(BaseModel):
    source_en: str = Field(min_length=1, max_length=512)
    target_cn: str = Field(min_length=1, max_length=512)


class TranslationBatch(BaseModel):
    items: list[TranslationItem]


TARGETS = {
    "circuits": {
        "table": "mirror_region_circuits",
        "id_col": "id",
        "source_col": "circuit_name",
        "cn_col": "name_cn",
    },
    "terms": {
        "table": "ontology_terms",
        "id_col": "id",
        "source_col": "canonical_term_en",
        "cn_col": "canonical_term_cn",
    },
}


async def load_missing(scope: str) -> list[tuple[str, str]]:
    target = TARGETS[scope]
    sql = text(
        f"SELECT {target['id_col']}::text, {target['source_col']} "
        f"FROM {target['table']} "
        f"WHERE ({target['cn_col']} IS NULL OR trim({target['cn_col']}) = '') "
        f"AND {target['source_col']} IS NOT NULL AND trim({target['source_col']}) <> '' "
        f"ORDER BY {target['source_col']} LIMIT 200000"
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(sql)).all()
    return [(str(r[0]), str(r[1])) for r in rows]


def _build_prompt(batch: list[tuple[str, str]]) -> tuple[str, str]:
    system = "You are a strict JSON API. Reply only with the requested JSON object. Never explain."
    items = [{"source_en": source} for _id, source in batch]
    user = (
        "Translate each neuroscience term into simplified Chinese. "
        'Return JSON exactly like: {"items": [{"source_en": "<en>", "target_cn": "<中文>"}]}. '
        f"Input: {json.dumps(items, ensure_ascii=False)}"
    )
    return system, user


def _parse(raw_text: str) -> TranslationBatch:
    text_value = (raw_text or "").strip()
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", text_value, re.DOTALL)
    if fence:
        text_value = fence.group(1).strip()
    parsed = json.loads(text_value)
    if isinstance(parsed, list):
        parsed = {"items": parsed}
    return TranslationBatch.model_validate(parsed)


async def apply_updates(scope: str, updates: list[tuple[str, str]]) -> int:
    target = TARGETS[scope]
    updated = 0
    async with AsyncSessionLocal() as session:
        for row_id, cn in updates:
            result = await session.execute(
                text(
                    f"UPDATE {target['table']} SET {target['cn_col']} = :cn "
                    f"WHERE {target['id_col']}::text = :id "
                    f"AND ({target['cn_col']} IS NULL OR trim({target['cn_col']}) = '')"
                ),
                {"cn": cn, "id": row_id},
            )
            updated += result.rowcount or 0
            if scope == "terms":
                session.add(
                    OntologyChangeLog(
                        action_type="term.chinese_fill",
                        entity_type="ontology_term",
                        entity_id=uuid.UUID(row_id),
                        before_data={},
                        after_data={"canonical_term_cn": cn},
                        operator_id="system:zh_fill",
                        reason="fill missing Chinese canonical name",
                    )
                )
        await session.commit()
    return updated


async def process_batch(
    scope: str,
    batch: list[tuple[str, str]],
    stats: Counter,
    records: list[dict],
    provider,
) -> None:
    cfg = get_settings()
    system_prompt, user_prompt = _build_prompt(batch)
    parsed: TranslationBatch | None = None
    parse_status = "provider_error"
    retry_count = 0
    raw_response = ""
    for attempt in range(2):
        retry_count = attempt
        try:
            if attempt == 0:
                response = await provider.complete_json(
                    model=cfg.ontology_residual_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.1,
                    max_tokens=cfg.ontology_residual_max_tokens,
                )
                raw_response = response.raw_text or ""
                if response.parsed_json is not None:
                    parsed = TranslationBatch.model_validate(response.parsed_json)
                else:
                    parsed = _parse(raw_response)
            else:
                retry_user = user_prompt + (
                    "\n\nIMPORTANT: Respond with ONLY the raw JSON object. "
                    "No reasoning or text outside JSON."
                )
                text_result = await provider.complete_text(
                    model=cfg.ontology_residual_model,
                    system_prompt=system_prompt,
                    user_prompt=retry_user,
                    temperature=0.2,
                    max_tokens=cfg.ontology_residual_max_tokens,
                    json_mode=False,
                )
                raw_response = text_result.raw_text or ""
                parsed = _parse(raw_response)
            parse_status = "ok"
            break
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            parse_status = "schema_error" if isinstance(exc, ValidationError) else "parse_error"
            if attempt == 0:
                await asyncio.sleep(cfg.ontology_residual_backoff_seconds)
                continue
    updates: list[tuple[str, str]] = []
    if parsed is not None:
        by_source = {item.source_en: item.target_cn for item in parsed.items}
        for row_id, source in batch:
            cn = by_source.get(source)
            if cn:
                updates.append((row_id, cn))
                stats["filled"] += 1
            else:
                stats["missed"] += 1
        if updates:
            stats["updated_rows"] += await apply_updates(scope, updates)
    else:
        stats["failed_batches"] += 1
    records.append(
        {
            "scope": scope,
            "model": cfg.ontology_residual_model,
            "prompt_version": PROMPT_VERSION,
            "raw_response": raw_response[:2000],
            "parse_status": parse_status,
            "retry_count": retry_count,
            "batch_size": len(batch),
        }
    )
    print(
        f"[{scope}] batch of {len(batch)} done filled={stats['filled']} "
        f"parse={parse_status}",
        flush=True,
    )


async def main(scope: str) -> None:
    cfg = get_settings()
    provider = get_llm_provider("deepseek")
    missing = await load_missing(scope)
    stats: Counter = Counter({"filled": 0, "missed": 0, "updated_rows": 0, "failed_batches": 0})
    records: list[dict] = []
    batches = [
        missing[i : i + cfg.ontology_residual_batch_size]
        for i in range(0, len(missing), cfg.ontology_residual_batch_size)
    ]
    semaphore = asyncio.Semaphore(cfg.ontology_residual_concurrency)

    async def worker(batch):
        async with semaphore:
            await process_batch(scope, batch, stats, records, provider)

    await asyncio.gather(*(worker(batch) for batch in batches))
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, f"zh_fill_{scope}.json"), "w", encoding="utf-8") as f:
        json.dump({"stats": dict(stats), "records": records}, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(stats), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["circuits", "terms", "all"], default="all")
    args = parser.parse_args()
    if args.scope == "all":
        asyncio.run(main("circuits"))
        asyncio.run(main("terms"))
    else:
        asyncio.run(main(args.scope))
