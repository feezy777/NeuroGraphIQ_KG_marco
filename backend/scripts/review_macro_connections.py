"""Macro Connection Human Review 实施脚本(交互式)。

对最新 validation run 的 REVIEW_REQUIRED 条目构建 Review Queue,人工逐个决策:
    [a] approve             - 批准进入 promotion
    [r] reject              - 拒绝(不可进入 Final)
    [n] needs_more_evidence - 证据不足,等待补充
决策永不自动生成("不要自动通过")。

两种运行方式:
1. 交互式(默认):  python scripts/review_macro_connections.py --reviewer feezy
2. 决策文件批量:    python scripts/review_macro_connections.py --reviewer feezy \\
                        --decisions-file data/export_review_decisions.json
   决策文件格式: {"<canonical_connection_id>": {"action": "approved|rejected|needs_more_evidence",
                                                "note": "..."}}
   先生成模板:  python scripts/review_macro_connections.py --generate-template <out.json>

输出: data/exports/macro_connection_promotion/review_summary.json
不执行:promotion、active 状态修改、Final KG 写入、CN2 inference、外部数据导入。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_connection_review_promotion_service import (
    VALID_ACTIONS,
    build_review_queue,
    latest_review_decision,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_promotion"


async def load_latest_validation(session) -> tuple[str | None, list[dict]]:
    """最新 validation run(id + REVIEW_REQUIRED results)。"""
    run_id = (await session.execute(text(
        "SELECT id FROM canonical_connection_validation_runs "
        "WHERE validator_key='macro_connection_validation_v1' ORDER BY created_at DESC LIMIT 1"
    ))).scalar()
    if not run_id:
        return None, []
    results = (await session.execute(text(
        """SELECT entity_id, failed_rules FROM canonical_connection_validation_results
           WHERE run_id=:rid AND validation_status='REVIEW_REQUIRED'"""), {"rid": run_id})).all()
    return str(run_id), [{"entity_id": str(r.entity_id),
                          "failed_rules": r.failed_rules} for r in results]


async def main(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as session:
        val_run_id, review_items = await load_latest_validation(session)
        if not review_items:
            print("no REVIEW_REQUIRED items in latest validation run")
            return
        print(f"validation_run: {val_run_id} | review queue: {len(review_items)}")

        ids = [r["entity_id"] for r in review_items]
        canon_rows = (await session.execute(text(
            """SELECT id, connection_code, source_region_id, target_region_id,
                      connection_type, directionality_policy, evidence_count,
                      evidence_summary, provenance_json, confidence_statistics
               FROM canonical_connections WHERE id = ANY(:ids)"""),
            {"ids": ids})).all()
        canon_by_id = {str(c.id): c for c in canon_rows}
        region_ids = {str(r[0]) for row in canon_rows
                      for r in [(row.source_region_id,), (row.target_region_id,)]}
        region_rows = (await session.execute(text(
            "SELECT id, canonical_name_en, canonical_name_cn FROM canonical_brain_regions "
            "WHERE id = ANY(:rids)"), {"rids": list(region_ids)})).all()
        region_names = {str(r.id): {"canonical_name_en": r.canonical_name_en,
                                    "canonical_name_cn": r.canonical_name_cn}
                        for r in region_rows}
        existing = (await session.execute(text(
            "SELECT canonical_connection_id, action, reviewer, created_at "
            "FROM canonical_connection_review_records"))).all()
        reviews = [{"canonical_connection_id": str(r[0]), "action": r[1],
                    "reviewer": r[2], "created_at": r[3]} for r in existing]

        items = []
        for r in review_items:
            c = canon_by_id.get(r["entity_id"])
            if not c:
                continue
            items.append({
                "canonical_connection_id": str(c.id),
                "connection_code": c.connection_code,
                "source_region_id": str(c.source_region_id),
                "target_region_id": str(c.target_region_id),
                "connection_type": c.connection_type,
                "directionality_policy": c.directionality_policy,
                "evidence_count": c.evidence_count or 0,
                "evidence_summary": c.evidence_summary or {},
                "provenance_json": c.provenance_json or {},
                "confidence_statistics": c.confidence_statistics or {},
                "validation_status": "REVIEW_REQUIRED",
                "validation_run_id": val_run_id,
                "failed_rules": r["failed_rules"],
            })
        queue = build_review_queue(items, region_names)

        if args.generate_template:
            _write_template(args.generate_template, queue)
            return

        # ---- 决策收集 ----
        decisions: dict[str, dict] = {}
        if args.decisions_file:
            decisions = json.loads(Path(args.decisions_file).read_text(encoding="utf-8"))
        else:
            decisions = _interactive(queue, args.reviewer)

        # ---- 校验 + 落库 ----
        applied, skipped, errors = 0, 0, 0
        for q in queue:
            cid = q["canonical_connection_id"]
            dec = decisions.get(cid)
            if not dec:
                print(f"[skip] {cid[:8]} no decision")
                skipped += 1
                continue
            action = dec.get("action")
            if action not in VALID_ACTIONS:
                print(f"[err] {cid[:8]} invalid action: {action}")
                errors += 1
                continue
            prev = latest_review_decision(reviews, cid)
            await session.execute(text(
                """INSERT INTO canonical_connection_review_records
                   (id, canonical_connection_id, validation_run_id, action, reviewer,
                    reviewer_note, failed_rules_json, before_json, after_json,
                    evidence_summary_json)
                   VALUES (:id, :cid, :vr, :act, :rev, :note, :fr, :before, :after, :es)"""),
                {"id": str(uuid.uuid4()), "cid": cid, "vr": val_run_id, "act": action,
                 "rev": args.reviewer, "note": dec.get("note"),
                 "fr": json.dumps(q["failed_rules"], ensure_ascii=False),
                 "before": json.dumps({
                     "source_region_id": q["source_region"]["region_id"],
                     "target_region_id": q["target_region"]["region_id"],
                     "connection_type": q["connection_type"],
                     "evidence_count": q["evidence_count"],
                     "validation_status": "REVIEW_REQUIRED"}, ensure_ascii=False),
                 "after": json.dumps({"action": action, "reviewer": args.reviewer},
                                     ensure_ascii=False),
                 "es": json.dumps(q["evidence_summary"], ensure_ascii=False)})
            print(f"[ok] {cid[:8]} {action} (prev={prev['action'] if prev else '-'})")
            applied += 1
        await session.commit()
        print(f"\napplied {applied} | skipped {skipped} | errors {errors}")

        # ---- 报告 ----
        _export_review_summary(queue, decisions, val_run_id, args.reviewer)
        print(f"[ok] review_summary.json -> {OUT_DIR}")


def _interactive(queue: list[dict], reviewer: str) -> dict:
    print(f"\n=== Macro Connection Review Queue ({len(queue)} items, reviewer: {reviewer}) ===")
    print("  [a]pprove  [r]eject  [n]eeds_more_evidence  <Enter>=skip  q=quit")
    decisions: dict[str, dict] = {}
    for i, q in enumerate(queue, 1):
        src = q["source_region"]["name_en"] or q["source_region"]["region_id"]
        tgt = q["target_region"]["name_en"] or q["target_region"]["region_id"]
        print(f"\n--- {i}/{len(queue)} ---")
        print(f"  connection : {q['connection_code']} ({q['canonical_connection_id'][:8]})")
        print(f"  regions    : {src} -> {tgt}")
        print(f"  type/dir   : {q['connection_type']} / {q['directionality_policy']}")
        print(f"  evidence   : count={q['evidence_count']} "
              f"provenance={'present' if q['provenance_json'] else 'MISSING'} "
              f"confidence={q['confidence_statistics'].get('count', 0)}")
        for fr in q["failed_rules"]:
            print(f"  failed rule: {fr['rule_code']} ({fr['category']}) - {fr['message']}")
        note = ""
        while True:
            raw = input("  decision (a/r/n, Enter=skip, q=quit): ").strip().lower()
            if raw in ("", "q"):
                if raw == "q":
                    print("quit; remaining items skipped")
                    return decisions
                break
            if raw in ("a", "r", "n"):
                act = {"a": "approved", "r": "rejected", "n": "needs_more_evidence"}[raw]
                note = input("  note (optional): ").strip()
                decisions[q["canonical_connection_id"]] = {"action": act, "note": note}
                break
            print("  invalid; use a/r/n/Enter/q")
    return decisions


def _write_template(path: str, queue: list[dict]) -> None:
    tpl = {}
    for q in queue:
        tpl[q["canonical_connection_id"]] = {
            "action": "", "note": "reviewer note",
            "_context": {
                "connection_code": q["connection_code"],
                "source": q["source_region"]["name_en"],
                "target": q["target_region"]["name_en"],
                "type": q["connection_type"],
                "evidence_count": q["evidence_count"],
                "failed_rules": [fr["rule_code"] for fr in q["failed_rules"]],
            },
        }
    Path(path).write_text(json.dumps(tpl, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"template -> {path} (fill 'action': approved|rejected|needs_more_evidence)")


def _export_review_summary(queue: list[dict], decisions: dict[str, dict],
                           val_run_id: str | None, reviewer: str) -> None:
    counts = {"approved": 0, "rejected": 0, "needs_more_evidence": 0, "skipped": 0}
    by_rule: dict[str, int] = defaultdict(int)
    items = []
    for q in queue:
        cid = q["canonical_connection_id"]
        dec = decisions.get(cid)
        action = dec.get("action") if dec else "skipped"
        counts[action] += 1
        for fr in q["failed_rules"]:
            by_rule[fr["rule_code"]] += 1
        items.append({
            "canonical_connection_id": cid,
            "connection_code": q["connection_code"],
            "source_region_name": q["source_region"]["name_en"],
            "target_region_name": q["target_region"]["name_en"],
            "connection_type": q["connection_type"],
            "evidence_count": q["evidence_count"],
            "failed_rules": [fr["rule_code"] for fr in q["failed_rules"]],
            "decision": action,
            "note": (dec or {}).get("note"),
        })
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "review_summary.json").write_text(json.dumps({
        "reviewer": reviewer,
        "validation_run_id": val_run_id,
        "total": len(queue),
        "approved": counts["approved"],
        "rejected": counts["rejected"],
        "needs_more_evidence": counts["needs_more_evidence"],
        "skipped": counts["skipped"],
        "failed_rule_counts": dict(sorted(by_rule.items(), key=lambda kv: -kv[1])),
        "items": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Macro Connection Human Review")
    parser.add_argument("--reviewer", default="human_reviewer")
    parser.add_argument("--decisions-file", default=None)
    parser.add_argument("--generate-template", default=None)
    args = parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(args))
