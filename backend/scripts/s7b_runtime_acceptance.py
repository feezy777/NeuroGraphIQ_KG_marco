# -*- coding: utf-8 -*-
"""S7B 运行时验收:仅对已验证的 _e2e 隔离库执行,数据带唯一前缀,只清理本脚本创建的显式 ID。

流程:
1. linked approved fixture → 回退 → 校验旧 review/item/统计/navigation
2. 重新 build 新评分 → revision=2 + supersedes 链 → approve → 历史查询
3. linked promoted fixture → 回退 → evidence invalidated + 置信度回算
4. 重复回退 → 409
5. standalone fixture → 新单对象任务
6. 仅删除本次 fixture 的明确 ID(不删迁移结构)
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from unittest.mock import patch

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.services import paper_evidence_service as pes  # noqa: E402

PREFIX = f"s7b-acc-{uuid.uuid4().hex[:8]}"
print(f"[S7B acceptance] fixture prefix: {PREFIX}")

CREATED: dict[str, list[str]] = {
    "tasks": [], "items": [], "reviews": [], "evidence": [], "targets": [], "papers": [],
}


async def make_task(session, status="pending") -> str:
    tid = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO paper_evidence_tasks "
            "(id, target_type, scope, mode, max_papers_per_object, status, review_status, summary, name) "
            "VALUES (:tid, 'connection', 'selected', 'existence', 3, :st, 'not_started', '{}'::jsonb, :name)"
        ),
        {"tid": tid, "st": status, "name": PREFIX},
    )
    CREATED["tasks"].append(tid)
    return tid


async def add_item(session, task_id, target_id, status="awaiting_review") -> str:
    iid = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO paper_evidence_task_items "
            "(id, task_id, target_type, target_id, label, current_confidence, status) "
            "VALUES (:iid, :tid, 'connection', :oid, :lbl, NULL, :st)"
        ),
        {"iid": iid, "tid": task_id, "oid": target_id, "lbl": f"{PREFIX}-{target_id[:6]}", "st": status},
    )
    CREATED["items"].append(iid)
    return iid


async def make_connection(session, target_id, confidence=0.5) -> None:
    await session.execute(
        text(
            "INSERT INTO mirror_region_connections "
            "(id, source_region_name_en, target_region_name_en, connection_type, directionality, "
            "granularity_level, source_atlas, mirror_status, review_status, confidence) "
            "VALUES (:id, :p, :p, 'projection', 'unidirectional', 'macro_clinical', 'test', "
            "'llm_suggested', 'pending', :conf)"
        ),
        {"id": target_id, "p": f"{PREFIX}-A", "conf": confidence},
    )
    CREATED["targets"].append(target_id)


async def make_paper(session) -> tuple[str, str]:
    pid = str(uuid.uuid4())
    pmid = f"9{uuid.uuid4().hex[:7]}"
    await session.execute(
        text(
            "INSERT INTO paper_sources (id, source, pmid, title, journal, publication_year, is_oa) "
            "VALUES (:id, 'europepmc', :pmid, :title, 'Neuro J', 2026, false)"
        ),
        {"id": pid, "pmid": pmid, "title": PREFIX},
    )
    CREATED["papers"].append(pid)
    return pid, pmid


async def build(session, *, task_id=None, item_id=None, target=None, paper_id=None, direction="supports", passages=None):
    r = await pes.build_review(
        session,
        target_type="connection",
        target_id=uuid.UUID(target),
        paper_id=uuid.UUID(paper_id) if paper_id else None,
        task_id=uuid.UUID(task_id) if task_id else None,
        task_item_id=uuid.UUID(item_id) if item_id else None,
        reviewer_id=None,
        claim_version="v1",
        claim_text_snapshot="acceptance claim",
        claim_components_snapshot=[],
        model_direction=None,
        model_assessment=None,
        reviewer_direction=direction,
        reviewer_evidence_level="direct",
        reviewer_confidence=0.7,
        reviewer_note=None,
        coverage_summary_snapshot={},
        coverage_formula_version="v1",
        draft_revision=0,
        passages=passages or [],
    )
    CREATED["reviews"].append(r["review_id"])
    return r


async def main() -> None:
    async with AsyncSessionLocal() as s:
        # ── 1. linked approved fixture → 回退 ──
        tid = await make_task(s)
        target = str(uuid.uuid4())
        iid = await add_item(s, tid, target)
        r = await build(s, task_id=tid, item_id=iid, target=target)
        await pes.approve_review(s, uuid.UUID(r["review_id"]), operator_id=f"{PREFIX}-rev")
        resp = await pes.rollback_review_for_rescore(
            s, uuid.UUID(r["review_id"]), reason=f"{PREFIX}-reason-1", actor=f"{PREFIX}-rev"
        )
        print("[1] linked approved rollback:", {k: resp[k] for k in ("revision_no", "promotion_rollback")})
        assert resp["revision_no"] == 2 and resp["promotion_rollback"] == "not_needed"
        assert resp["navigation"]["task_id"] == tid and resp["navigation"]["task_item_id"] == iid
        row = dict((await s.execute(text("SELECT * FROM paper_evidence_reviews WHERE id=:r"), {"r": r["review_id"]})).first()._mapping)
        assert row["review_status"] == "approved" and row["superseded_at"] is not None
        item = dict((await s.execute(text("SELECT * FROM paper_evidence_task_items WHERE id=:i"), {"i": iid})).first()._mapping)
        assert item["status"] == "awaiting_review" and item["rescore_revision_no"] == 2
        t = (await s.execute(text("SELECT processed_items, awaiting_review_items FROM paper_evidence_tasks WHERE id=:t"), {"t": tid})).first()
        print("[1] old review superseded; item awaiting_review; task counts:", t[0], t[1])
        assert t[0] == 0 and t[1] == 1

        # ── 2. 重复回退 409 ──
        try:
            await pes.rollback_review_for_rescore(s, uuid.UUID(r["review_id"]), reason="again", actor="x")
            raise SystemExit("[2] FAIL: duplicate rollback did not raise")
        except pes.ReviewConflictError as exc:
            print("[2] duplicate rollback → 409 code:", exc.code)
            assert exc.code == "REVIEW_ALREADY_SUPERSEDED"

        # ── 3. 重新 build 新评分 → revision=2 + supersedes 链 → approve → 历史 ──
        r2 = await build(s, task_id=tid, item_id=iid, target=target)
        row2 = dict((await s.execute(text("SELECT * FROM paper_evidence_reviews WHERE id=:r"), {"r": r2["review_id"]})).first()._mapping)
        assert row2["revision_no"] == 2 and str(row2["supersedes_review_id"]) == r["review_id"]
        item2 = dict((await s.execute(text("SELECT * FROM paper_evidence_task_items WHERE id=:i"), {"i": iid})).first()._mapping)
        assert item2["rescore_source_review_id"] is None  # 上下文已清
        await pes.approve_review(s, uuid.UUID(r2["review_id"]), operator_id=f"{PREFIX}-rev")
        hist = await pes.get_review_history(s, uuid.UUID(r2["review_id"]))
        assert [h["review_id"] for h in hist["items"]] == [r["review_id"], r2["review_id"]]
        assert hist["items"][1]["is_current"] is True and hist["items"][0]["is_current"] is False
        print("[3] new revision chain:", [(h["revision_no"], h["is_current"]) for h in hist["items"]])

        # ── 4. linked promoted fixture → 回退 → evidence invalidated + 置信度回算 ──
        tid2 = await make_task(s)
        target2 = str(uuid.uuid4())
        await make_connection(s, target2, confidence=0.5)
        iid2 = await add_item(s, tid2, target2)
        pid, pmid = await make_paper(s)
        rp = await build(s, task_id=tid2, item_id=iid2, target=target2, paper_id=pid, passages=[{
            "passage": f"{PREFIX} projects via direct pathways.",
            "source_scope": "abstract",
            "direction": "supports",
            "evidence_level": "direct",
            "reason": "explicit",
            "confidence": 0.85,
            "source_verified": True,
            "source_verification_method": "exact",
            "source_locator": "abstract:0",
            "supported_components": ["source_region", "target_region", "relation"],
            "is_selected": True,
        }])
        await pes.approve_review(s, uuid.UUID(rp["review_id"]), operator_id=f"{PREFIX}-rev")
        mock_paper = {
            "pmid": pmid, "doi": f"10.1/{PREFIX}", "title": f"{PREFIX}-paper", "journal": "Neuro J",
            "year": "2026", "authors": "A B", "abstract": f"{PREFIX} projects via direct pathways.",
            "source": "europepmc",
        }
        with patch.object(pes, "verify_paper", return_value=mock_paper), patch.object(
            pes, "_load_source", return_value=(f"{PREFIX} projects via direct pathways.", "abstract")
        ):
            pr = await pes.promote_review(s, uuid.UUID(rp["review_id"]), promoted_by=f"{PREFIX}-rev")
        CREATED["evidence"].append(pr["evidence_id"])
        before_conf = (await s.execute(text("SELECT confidence FROM mirror_region_connections WHERE id=:t"), {"t": target2})).scalar_one()
        resp2 = await pes.rollback_review_for_rescore(
            s, uuid.UUID(rp["review_id"]), reason=f"{PREFIX}-reason-2", actor=f"{PREFIX}-rev"
        )
        assert resp2["promotion_rollback"] == "completed"
        ev_status = (await s.execute(text("SELECT verification_status FROM mirror_evidence_records WHERE id=:e"), {"e": pr["evidence_id"]})).scalar_one()
        after_conf = (await s.execute(text("SELECT confidence FROM mirror_region_connections WHERE id=:t"), {"t": target2})).scalar_one()
        print("[4] promoted rollback: evidence", ev_status, "| confidence", before_conf, "→", after_conf)
        assert ev_status == "invalidated"
        assert after_conf is None or after_conf <= before_conf

        # ── 5. standalone fixture → 新单对象任务 ──
        target3 = str(uuid.uuid4())
        await make_connection(s, target3, confidence=0.42)
        rid3 = str(uuid.uuid4())
        await s.execute(
            text(
                "INSERT INTO paper_evidence_reviews "
                "(id, target_type, target_id, review_status, promotion_status, revision_no, "
                "reviewed_at, approved_at, reviewer_direction, reviewer_confidence, claim_version, "
                "claim_text_snapshot, reviewer_note) "
                "VALUES (:id, 'connection', :tgt, 'approved', 'not_ready', 1, now(), now(), "
                "'supports', 0.7, 'v1', :p, :p)"
            ),
            {"id": rid3, "tgt": target3, "p": PREFIX},
        )
        CREATED["reviews"].append(rid3)
        resp3 = await pes.rollback_review_for_rescore(
            s, uuid.UUID(rid3), reason=f"{PREFIX}-reason-3", actor=f"{PREFIX}-rev"
        )
        new_tid = resp3["navigation"]["task_id"]
        CREATED["tasks"].append(new_tid)
        CREATED["items"].append(resp3["navigation"]["task_item_id"])
        nt = (await s.execute(text("SELECT scope, name, filter_snapshot FROM paper_evidence_tasks WHERE id=:t"), {"t": new_tid})).first()
        print("[5] standalone new task:", nt[0], "|", nt[1], "|", nt[2])
        assert nt[0] == "single_object" and nt[2] == {"rescore_of": rid3}

        print("\n[S7B acceptance] ALL CHECKS PASSED")

        # ── 6. 清理:仅删除本脚本创建的显式 ID(FK 安全顺序) ──
        ids = [uuid.UUID(r) for r in CREATED["reviews"]]
        # 6a) 清 item 的 rescore FK(指向待删 review)
        await s.execute(
            text("UPDATE paper_evidence_task_items SET rescore_source_review_id=NULL, rescore_revision_no=NULL "
                 "WHERE rescore_source_review_id = ANY(:ids)"),
            {"ids": ids},
        )
        # 6b) items/tasks
        for iid in CREATED["items"]:
            await s.execute(text("DELETE FROM paper_evidence_task_items WHERE id=:i"), {"i": iid})
        for tid in CREATED["tasks"]:
            await s.execute(text("DELETE FROM paper_evidence_task_items WHERE task_id::text=:t"), {"t": str(tid)})
            await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:t"), {"t": str(tid)})
        # 6c) review 链拓扑删(子先父后)
        for _ in range(len(ids) + 2):
            for rid in list(ids):
                child = (
                    await s.execute(
                        text("SELECT 1 FROM paper_evidence_reviews WHERE supersedes_review_id=:r AND id = ANY(:ids)"),
                        {"r": rid, "ids": ids},
                    )
                ).first()
                if child is None:
                    await s.execute(text("DELETE FROM paper_evidence_review_passages WHERE review_id=:r"), {"r": rid})
                    await s.execute(text("DELETE FROM paper_evidence_reviews WHERE id=:r"), {"r": rid})
                    ids.remove(rid)
            if not ids:
                break
        # 6d) evidence/targets/papers
        for eid in CREATED["evidence"]:
            await s.execute(text("DELETE FROM mirror_evidence_passages WHERE evidence_id=:e"), {"e": eid})
            await s.execute(text("DELETE FROM confidence_adjustment_logs WHERE evidence_id=:e"), {"e": eid})
            await s.execute(text("DELETE FROM mirror_evidence_records WHERE id=:e"), {"e": eid})
        for tgt in CREATED["targets"]:
            await s.execute(text("DELETE FROM mirror_region_connections WHERE id=:t"), {"t": tgt})
        for pid_ in CREATED["papers"]:
            await s.execute(text("DELETE FROM paper_sources WHERE id=:p"), {"p": pid_})
        await s.commit()
        print(f"[S7B acceptance] cleaned {sum(len(v) for v in CREATED.values())} fixture rows (prefix {PREFIX})")


asyncio.run(main())
