"""Backfill missing fields for molecular_attr circuit steps and functions.

Targets:
  mirror_circuit_steps  — description, uncertainty_reason
  mirror_circuit_functions — description, evidence_level

Uses DeepSeek v4-pro, batch of 30 items per LLM call.
Keyset pagination (cursor-based), resume-safe via --skip.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import selectors
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.services.llm_providers import get_llm_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_molecular")

BATCH_SIZE = 50
CONCURRENCY = 5  # parallel LLM calls
MODEL = "deepseek-chat"
PROVIDER = "deepseek"
GRANULARITY = "molecular_attr"
DRY_RUN = "--dry-run" in sys.argv
STEPS_ONLY = "--steps-only" in sys.argv
FUNCS_ONLY = "--funcs-only" in sys.argv

# ── Prompt templates ──────────────────────────────────────────────────────

STEP_SYSTEM = """You are a neuroscience expert. Complete missing fields for ALL circuit steps.
Output EXACTLY one JSON object per line, nothing else. No markdown, no explanation.
Each line must be: {"step_index": N, "description": "...", "uncertainty_reason": "..."}
For descriptions, use Chinese. If evidence is thin, start with "推测:".
For uncertainty_reason, use Chinese: "仅基于连接组推断", "层特异性投射已有文献支持", "跨物种同源性推断", "直接证据充分", etc."""

STEP_USER_TEMPLATE = """Circuit: {circuit_name} ({circuit_type})
Desc: {circuit_desc}
Func: {circuit_func}

Output one JSON object per line for each step below (no commas between lines, no outer array brackets):
{steps_json}"""

FUNC_SYSTEM = """You are a neuroscience expert. Complete missing fields for ALL circuit functions.
Output EXACTLY one JSON object per line, nothing else. No markdown, no explanation.
Each line must be: {"func_index": N, "description": "...", "evidence_level": "low|moderate|high|insufficient"}
For descriptions, use Chinese. If speculative, start with "推测:".
For evidence_level, most molecular Allen HBA functions should be "low" or "insufficient"."""

FUNC_USER_TEMPLATE = """Circuit: {circuit_name} ({circuit_type})
Desc: {circuit_desc}
Func: {circuit_func}

Output one JSON object per line for each function below (no commas between lines, no outer array brackets):
{funcs_json}"""


# ── Core logic ────────────────────────────────────────────────────────────

async def _load_circuit_info(session, circuit_ids: set) -> dict:
    """Batch-load circuit name, type, description, function_association."""
    if not circuit_ids:
        return {}
    rows = await session.execute(
        text("""SELECT id, circuit_name, circuit_type, description, function_association
                FROM mirror_region_circuits WHERE id = ANY(:ids)"""),
        {"ids": list(circuit_ids)},
    )
    return {r[0]: {"name": r[1] or "unknown", "type": r[2] or "unknown",
                   "desc": r[3] or "", "func": r[4] or ""} for r in rows}


def _parse_line_by_line(raw_text: str) -> list[dict]:
    """Parse model response as JSON objects, one per line. Handles missing commas."""
    results = []
    lines = raw_text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line or line in ("]", "]}", "}", "])"):
            continue
        # Try direct parse
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                results.append(obj)
            continue
        except json.JSONDecodeError:
            pass
        # Try stripping trailing comma
        if line.endswith(","):
            try:
                obj = json.loads(line[:-1])
                if isinstance(obj, dict):
                    results.append(obj)
                continue
            except json.JSONDecodeError:
                pass
    return results


async def _llm_complete_and_parse(provider, system: str, user: str, max_retries: int = 3):
    """Call DeepSeek complete_text, parse response line-by-line as JSON objects. Retry on failure."""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            result = await provider.complete_text(
                model=MODEL,
                system_prompt=system,
                user_prompt=user,
                temperature=0.2,
                max_tokens=4096,
                timeout_seconds=120,
            )
            if not result.raw_text:
                raise ValueError("empty response")
            items = _parse_line_by_line(result.raw_text)
            if not items:
                logger.warning("No JSON objects parsed from response (attempt %d), raw[:200]: %s",
                               attempt, (result.raw_text or "")[:200])
                raise ValueError("no parseable objects in response")
            return items, (result.usage.total_tokens or 0)
        except ValueError as exc:
            last_err = exc
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning("Parse failed (attempt %d/%d), retrying in %ds: %s",
                               attempt, max_retries, wait, str(exc)[:80])
                await asyncio.sleep(wait)
        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning("LLM call failed (attempt %d/%d), retrying in %ds: %s", attempt, max_retries, wait, exc)
                await asyncio.sleep(wait)
    raise last_err  # type: ignore


async def _process_step_batch(provider, batch, circuit_cache, session):
    """Process one batch: build prompt, call LLM, update DB. Returns (updated, tokens, batch_size)."""
    cids = {r[1] for r in batch if r[1]}
    missing = cids - circuit_cache.keys()
    if missing:
        fresh = await _load_circuit_info(session, missing)
        circuit_cache.update(fresh)

    items = []
    for i, row in enumerate(batch):
        items.append({
            "step_index": i,
            "step_order": row[2],
            "step_name": row[3],
            "step_type": row[4],
            "role": row[5],
            "evidence_text": (row[6] or "")[:300],
        })

    cinfo = circuit_cache.get(batch[0][1], {"name": "unknown", "type": "unknown", "desc": "", "func": ""})
    user_prompt = STEP_USER_TEMPLATE.format(
        count=len(items),
        circuit_name=cinfo["name"],
        circuit_type=cinfo["type"],
        circuit_desc=(cinfo["desc"] or "No description available")[:500],
        circuit_func=(cinfo["func"] or "No function recorded")[:300],
        steps_json=json.dumps(items, ensure_ascii=False),
    )

    if DRY_RUN:
        return 0, 0, len(batch)

    try:
        result_items, tokens = await _llm_complete_and_parse(provider, STEP_SYSTEM, user_prompt)
    except Exception as exc:
        logger.error("[steps] LLM failed: %s", str(exc)[:120])
        return 0, 0, len(batch)

    result_map = {}
    for ri in result_items:
        if isinstance(ri, dict) and "step_index" in ri:
            result_map[ri["step_index"]] = ri

    updated = 0
    for i, row in enumerate(batch):
        ri = result_map.get(i)
        if ri is None:
            continue
        desc = ri.get("description")
        unc = ri.get("uncertainty_reason")
        needs_desc = row[7] is None and isinstance(desc, str) and desc.strip()
        needs_unc = row[8] is None and isinstance(unc, str) and unc.strip()
        if not needs_desc and not needs_unc:
            continue
        sets, params = [], {"id": row[0]}
        if needs_desc:
            sets.append("description = :desc"); params["desc"] = desc.strip()[:2000]
        if needs_unc:
            sets.append("uncertainty_reason = :unc"); params["unc"] = unc.strip()[:2000]
        sets.append("updated_at = NOW()")
        await session.execute(text(f"UPDATE mirror_circuit_steps SET {', '.join(sets)} WHERE id = :id"), params)
        updated += 1

    return updated, tokens, len(batch)


async def backfill_steps(session, provider, circuit_map: dict):
    """Concurrent keyset pagination: backfill steps where description OR uncertainty_reason is NULL."""
    total = await session.execute(
        text("SELECT COUNT(*) FROM mirror_circuit_steps WHERE granularity_level = :g AND (description IS NULL OR uncertainty_reason IS NULL)"),
        {"g": GRANULARITY},
    )
    total = total.scalar()
    logger.info("[steps] Total needing backfill: %s (batch=%d, concurrent=%d)", total, BATCH_SIZE, CONCURRENCY)

    processed = 0
    batch_num = 0
    total_tokens = 0
    last_id = "00000000-0000-0000-0000-000000000000"
    t0 = time.monotonic()
    circuit_cache: dict = {}

    while True:
        # Fetch CONCURRENCY batches
        batches = []
        for _ in range(CONCURRENCY):
            rows = await session.execute(
                text("""SELECT s.id, s.circuit_id, s.step_order, s.step_name, s.step_type, s.role,
                               s.evidence_text, s.description, s.uncertainty_reason
                        FROM mirror_circuit_steps s
                        WHERE s.granularity_level = :g
                          AND (s.description IS NULL OR s.uncertainty_reason IS NULL)
                          AND s.id > :cursor
                        ORDER BY s.id
                        LIMIT :limit"""),
                {"g": GRANULARITY, "cursor": last_id, "limit": BATCH_SIZE},
            )
            batch = rows.fetchall()
            if not batch:
                break
            last_id = batch[-1][0]
            batches.append(batch)

        if not batches:
            break

        # Process all batches concurrently
        tasks = [_process_step_batch(provider, b, circuit_cache, session) for b in batches]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, result in enumerate(results):
            batch_num += 1
            if isinstance(result, Exception):
                logger.error("[steps] batch=%d exception: %s", batch_num, result)
                continue
            upd, tok, sz = result
            total_tokens += tok
            processed += sz
            if batch_num % 10 == 0:
                elapsed = time.monotonic() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total - processed) / rate if rate > 0 else 0
                logger.info("[steps] batch=%d updated=%d/%d progress=%d/%d rate=%.0f/s ETA=%.0fs",
                            batch_num, upd, sz, processed, total, rate, eta)

        await session.commit()

    elapsed = time.monotonic() - t0
    logger.info("[steps] DONE. processed=%d/%d tokens=%d elapsed=%.0fs", processed, total, total_tokens, elapsed)


async def _process_func_batch(provider, batch, circuit_cache, session):
    """Process one batch: build prompt, call LLM, update DB. Returns (updated, tokens, batch_size)."""
    cids = {r[1] for r in batch if r[1]}
    missing = cids - circuit_cache.keys()
    if missing:
        fresh = await _load_circuit_info(session, missing)
        circuit_cache.update(fresh)

    items = []
    for i, row in enumerate(batch):
        items.append({
            "func_index": i,
            "function_term_en": row[2] or "",
            "function_term_cn": row[3] or "",
            "function_domain": row[4] or "unknown",
            "function_role": row[5] or "unknown",
            "effect_type": row[6] or "unknown",
        })

    cinfo = circuit_cache.get(batch[0][1], {"name": "unknown", "type": "unknown", "desc": "", "func": ""})
    user_prompt = FUNC_USER_TEMPLATE.format(
        count=len(items),
        circuit_name=cinfo["name"],
        circuit_type=cinfo["type"],
        circuit_desc=(cinfo["desc"] or "No description available")[:500],
        circuit_func=(cinfo["func"] or "No function recorded")[:300],
        funcs_json=json.dumps(items, ensure_ascii=False),
    )

    if DRY_RUN:
        return 0, 0, len(batch)

    try:
        result_items, tokens = await _llm_complete_and_parse(provider, FUNC_SYSTEM, user_prompt)
    except Exception as exc:
        logger.error("[funcs] LLM failed: %s", str(exc)[:120])
        return 0, 0, len(batch)

    result_map = {}
    for ri in result_items:
        if isinstance(ri, dict) and "func_index" in ri:
            result_map[ri["func_index"]] = ri

    updated = 0
    for i, row in enumerate(batch):
        ri = result_map.get(i)
        if ri is None:
            continue
        desc = ri.get("description")
        evl = ri.get("evidence_level")
        needs_desc = row[7] is None and isinstance(desc, str) and desc.strip()
        needs_evl = (row[8] is None and isinstance(evl, str) and evl.strip()
                     and evl.strip() in ("high", "moderate", "low", "insufficient"))
        if not needs_desc and not needs_evl:
            continue
        sets, params = [], {"id": row[0]}
        if needs_desc:
            sets.append("description = :desc"); params["desc"] = desc.strip()[:2000]
        if needs_evl:
            sets.append("evidence_level = :evl"); params["evl"] = evl.strip()
        sets.append("updated_at = NOW()")
        await session.execute(text(f"UPDATE mirror_circuit_functions SET {', '.join(sets)} WHERE id = :id"), params)
        updated += 1

    return updated, tokens, len(batch)


async def backfill_functions(session, provider, circuit_map: dict):
    """Concurrent keyset pagination: backfill functions where description OR evidence_level is NULL."""
    total = await session.execute(
        text("SELECT COUNT(*) FROM mirror_circuit_functions WHERE granularity_level = :g AND (description IS NULL OR evidence_level IS NULL)"),
        {"g": GRANULARITY},
    )
    total = total.scalar()
    logger.info("[funcs] Total needing backfill: %s (batch=%d, concurrent=%d)", total, BATCH_SIZE, CONCURRENCY)

    processed = 0
    batch_num = 0
    total_tokens = 0
    last_id = "00000000-0000-0000-0000-000000000000"
    t0 = time.monotonic()
    circuit_cache: dict = {}

    while True:
        batches = []
        for _ in range(CONCURRENCY):
            rows = await session.execute(
                text("""SELECT f.id, f.circuit_id, f.function_term_en, f.function_term_cn,
                               f.function_domain, f.function_role, f.effect_type,
                               f.description, f.evidence_level
                        FROM mirror_circuit_functions f
                        WHERE f.granularity_level = :g
                          AND (f.description IS NULL OR f.evidence_level IS NULL)
                          AND f.id > :cursor
                        ORDER BY f.id
                        LIMIT :limit"""),
                {"g": GRANULARITY, "cursor": last_id, "limit": BATCH_SIZE},
            )
            batch = rows.fetchall()
            if not batch:
                break
            last_id = batch[-1][0]
            batches.append(batch)

        if not batches:
            break

        tasks = [_process_func_batch(provider, b, circuit_cache, session) for b in batches]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, result in enumerate(results):
            batch_num += 1
            if isinstance(result, Exception):
                logger.error("[funcs] batch=%d exception: %s", batch_num, result)
                continue
            upd, tok, sz = result
            total_tokens += tok
            processed += sz
            if batch_num % 10 == 0:
                elapsed = time.monotonic() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total - processed) / rate if rate > 0 else 0
                logger.info("[funcs] batch=%d updated=%d/%d progress=%d/%d rate=%.0f/s ETA=%.0fs",
                            batch_num, upd, sz, processed, total, rate, eta)

        await session.commit()

    elapsed = time.monotonic() - t0
    logger.info("[funcs] DONE. processed=%d/%d tokens=%d elapsed=%.0fs", processed, total, total_tokens, elapsed)


async def main():
    provider = get_llm_provider(PROVIDER)
    circuit_map: dict = {}

    async with AsyncSessionLocal() as session:
        if not FUNCS_ONLY:
            await backfill_steps(session, provider, circuit_map)
        if not STEPS_ONLY:
            await backfill_functions(session, provider, circuit_map)

    logger.info("All done.")


if __name__ == "__main__":
    if DRY_RUN:
        logger.info("=== DRY RUN MODE (no writes, no LLM calls) ===")
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
