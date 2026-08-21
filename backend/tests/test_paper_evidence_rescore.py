# -*- coding: utf-8 -*-
"""S7B: 回退并重新评分(版本链)service/API 级测试。

约定:
- 写测试仅运行于已验证的 _e2e 隔离库(conftest 硬门禁);
- 清理仅按本测试创建的明确 ID 删除,严禁无条件 DELETE/TRUNCATE。
"""
from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ════════════════════════════════════════════════════════════════════════════
# Fixture helpers(全部按显式 ID 清理)
# ════════════════════════════════════════════════════════════════════════════


async def _make_task(session, raw_status="pending") -> str:
    tid = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO paper_evidence_tasks "
            "(id, target_type, scope, mode, max_papers_per_object, status, review_status, summary) "
            "VALUES (:tid, 'connection', 'selected', 'existence', 3, :st, 'not_started', '{}'::jsonb)"
        ),
        {"tid": tid, "st": raw_status},
    )
    await session.commit()
    return tid


async def _add_item(session, task_id: str, target_id: str, status="awaiting_review") -> str:
    iid = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO paper_evidence_task_items "
            "(id, task_id, target_type, target_id, label, current_confidence, status) "
            "VALUES (:iid, :tid, 'connection', :oid, :lbl, NULL, :st)"
        ),
        {"iid": iid, "tid": task_id, "oid": target_id, "lbl": target_id[:8], "st": status},
    )
    await session.commit()
    return iid


async def _make_connection(session, target_id: str, confidence: float | None = 0.5) -> str:
    await session.execute(
        text(
            "INSERT INTO mirror_region_connections "
            "(id, source_region_name_en, target_region_name_en, connection_type, directionality, "
            "granularity_level, source_atlas, mirror_status, review_status, confidence) "
            "VALUES (:id, 'A', 'B', 'projection', 'unidirectional', 'macro_clinical', 'test', "
            "'llm_suggested', 'pending', :conf)"
        ),
        {"id": target_id, "conf": confidence},
    )
    await session.commit()
    return target_id


async def _make_paper(session, pmid: str | None = None) -> tuple[str, str]:
    pid = str(uuid.uuid4())
    pmid = pmid or f"9{uuid.uuid4().hex[:7]}"
    await session.execute(
        text(
            "INSERT INTO paper_sources (id, source, pmid, title, journal, publication_year, is_oa) "
            "VALUES (:id, 'europepmc', :pmid, 'Test Paper', 'Neuro J', 2026, false)"
        ),
        {"id": pid, "pmid": pmid},
    )
    await session.commit()
    return pid, pmid


async def _build(session, *, task_id=None, task_item_id=None, target_id=None, direction="supports") -> dict:
    return await pes.build_review(
        session,
        target_type="connection",
        target_id=uuid.UUID(target_id or str(uuid.uuid4())),
        paper_id=None,
        task_id=uuid.UUID(task_id) if task_id else None,
        task_item_id=uuid.UUID(task_item_id) if task_item_id else None,
        reviewer_id=None,
        claim_version="v1",
        claim_text_snapshot="test claim",
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
        passages=[],
    )


async def _cleanup(
    session,
    *,
    task_ids: list[str] | None = None,
    item_ids: list[str] | None = None,
    review_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    target_ids: list[str] | None = None,
    paper_ids: list[str] | None = None,
) -> None:
    # 先删 item(task_item.rescore_source_review_id FK 指向 review),再删 review
    for iid in item_ids or []:
        await session.execute(text("DELETE FROM paper_evidence_task_items WHERE id=:i"), {"i": iid})
    for tid in task_ids or []:
        await session.execute(text("DELETE FROM paper_evidence_task_items WHERE task_id::text=:t"), {"t": tid})
        await session.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:t"), {"t": tid})
    ids = [uuid.UUID(r) for r in (review_ids or [])]
    # 拓扑序删链:先删子(supersedes 指向待删行),再删父;链深 ≤4 轮足够
    for _ in range(len(ids) + 2):
        for rid in list(ids):
            child = (
                await session.execute(
                    text("SELECT 1 FROM paper_evidence_reviews WHERE supersedes_review_id=:r AND id = ANY(:ids)"),
                    {"r": rid, "ids": ids},
                )
            ).first()
            if child is None:
                await session.execute(text("DELETE FROM paper_evidence_review_passages WHERE review_id=:r"), {"r": rid})
                await session.execute(text("DELETE FROM paper_evidence_reviews WHERE id=:r"), {"r": rid})
                ids.remove(rid)
        if not ids:
            break
    for eid in evidence_ids or []:
        await session.execute(text("DELETE FROM mirror_evidence_passages WHERE evidence_id=:e"), {"e": eid})
        await session.execute(text("DELETE FROM confidence_adjustment_logs WHERE evidence_id=:e"), {"e": eid})
        await session.execute(text("DELETE FROM mirror_evidence_records WHERE id=:e"), {"e": eid})
    for tid in target_ids or []:
        await session.execute(text("DELETE FROM mirror_region_connections WHERE id=:t"), {"t": tid})
    for pid in paper_ids or []:
        await session.execute(text("DELETE FROM paper_sources WHERE id=:p"), {"p": pid})
    await session.commit()


async def _review_row(session, review_id: str) -> dict:
    row = (
        await session.execute(
            text("SELECT * FROM paper_evidence_reviews WHERE id=:rid"), {"rid": review_id}
        )
    ).first()
    return dict(row._mapping) if row else {}


async def _item_row(session, item_id: str) -> dict:
    row = (
        await session.execute(
            text("SELECT * FROM paper_evidence_task_items WHERE id=:iid"), {"iid": item_id}
        )
    ).first()
    return dict(row._mapping) if row else {}


# 常用 fixture:linked approved review(approve 使 item completed)
async def _linked_approved_fixture(session):
    tid = await _make_task(session)
    target = str(uuid.uuid4())
    iid = await _add_item(session, tid, target)
    r = await _build(session, task_id=tid, task_item_id=iid, target_id=target)
    await pes.approve_review(session, uuid.UUID(r["review_id"]), operator_id="reviewer-1")
    return tid, iid, target, r["review_id"]


async def _linked_promoted_fixture(session):
    tid = await _make_task(session)
    target = str(uuid.uuid4())
    await _make_connection(session, target, confidence=0.5)
    iid = await _add_item(session, tid, target)
    pid, pmid = await _make_paper(session)
    r = await pes.build_review(
        session,
        target_type="connection",
        target_id=uuid.UUID(target),
        paper_id=uuid.UUID(pid),
        task_id=uuid.UUID(tid),
        task_item_id=uuid.UUID(iid),
        reviewer_id=None,
        claim_version="v1",
        claim_text_snapshot="test claim",
        claim_components_snapshot=[],
        model_direction=None,
        model_assessment=None,
        reviewer_direction="supports",
        reviewer_evidence_level="direct",
        reviewer_confidence=0.7,
        reviewer_note=None,
        coverage_summary_snapshot={},
        coverage_formula_version="v1",
        draft_revision=0,
        passages=[
            {
                "passage": "A projects to B via direct pathways.",
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
            }
        ],
    )
    await pes.approve_review(session, uuid.UUID(r["review_id"]), operator_id="reviewer-1")
    mock_paper = {
        "pmid": pmid,
        "doi": "10.1/test",
        "title": "Test Paper Title",
        "journal": "Neuro J",
        "year": "2026",
        "authors": "A B",
        "abstract": "A projects to B via direct pathways.",
        "source": "europepmc",
    }
    with patch.object(pes, "verify_paper", return_value=mock_paper), patch.object(
        pes, "_load_source", return_value=("A projects to B via direct pathways.", "abstract")
    ):
        pr = await pes.promote_review(session, uuid.UUID(r["review_id"]), promoted_by="reviewer-1")
    return tid, iid, target, r["review_id"], pr["evidence_id"], pid


# ════════════════════════════════════════════════════════════════════════════
# 1. 迁移与默认值
# ════════════════════════════════════════════════════════════════════════════


def test_migration_044_columns_present():
    async def case():
        async with AsyncSessionLocal() as s:
            cols = (
                await s.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='paper_evidence_reviews' AND column_name IN "
                        "('revision_no','supersedes_review_id','superseded_at','superseded_by','rollback_reason')"
                    )
                )
            ).scalars().all()
            assert len(cols) == 5
            item_cols = (
                await s.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='paper_evidence_task_items' AND column_name IN "
                        "('rescore_source_review_id','rescore_revision_no')"
                    )
                )
            ).scalars().all()
            assert len(item_cols) == 2
            fk = (
                await s.execute(
                    text(
                        "SELECT 1 FROM pg_constraint "
                        "WHERE conname='paper_evidence_task_items_rescore_source_review_id_fkey'"
                    )
                )
            ).first()
            assert fk is not None
    _run(case())


def test_old_review_defaults_revision_one():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            target = str(uuid.uuid4())
            iid = await _add_item(s, tid, target)
            r = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
            try:
                row = await _review_row(s, r["review_id"])
                assert row["revision_no"] == 1
                assert row["supersedes_review_id"] is None
                assert row["superseded_at"] is None
            finally:
                await _cleanup(s, task_ids=[tid], item_ids=[iid], review_ids=[r["review_id"]])
    _run(case())


# ════════════════════════════════════════════════════════════════════════════
# 2. linked approved 回退
# ════════════════════════════════════════════════════════════════════════════


def test_rollback_linked_approved():
    async def case():
        async with AsyncSessionLocal() as s:
            tid, iid, target, rid = await _linked_approved_fixture(s)
            try:
                result = await pes.rollback_review_for_rescore(
                    s, uuid.UUID(rid), reason="结论有误，重新评分", actor="reviewer-1"
                )
                assert result["promotion_rollback"] == "not_needed"
                assert result["revision_no"] == 2
                assert result["navigation"]["task_id"] == tid
                assert result["navigation"]["task_item_id"] == iid
                # 6) approved 事实保留;7) superseded 标记
                row = await _review_row(s, rid)
                assert row["review_status"] == "approved"
                assert row["approved_at"] is not None
                assert row["superseded_at"] is not None
                assert row["superseded_by"] == "reviewer-1"
                assert row["rollback_reason"] == "结论有误，重新评分"
                # 8) item 重开 + rescore 上下文;名称/置信度快照保留
                item = await _item_row(s, iid)
                assert item["status"] == "awaiting_review"
                assert item["rescore_source_review_id"] == uuid.UUID(rid)
                assert item["rescore_revision_no"] == 2
                assert item["reviewed_at"] is None and item["reviewed_by"] is None
                assert item["label"] == target[:8]
                assert item["evidence_id"] is None
                # 9) 任务统计与 work_status
                tasks = await pes.list_paper_evidence_tasks(s, limit=200)
                t = next(t for t in tasks["items"] if t["id"] == tid)
                assert t["item_counts"]["awaiting_review"] == 1
                assert t["item_counts"]["completed"] == 0
                assert t["work_status"] == "awaiting_review"
                # capability:superseded 不再开放
                can, block = await pes._review_rollback_capability(s, row)
                assert (can, block) == (False, "ALREADY_SUPERSEDED")
            finally:
                await _cleanup(s, task_ids=[tid], item_ids=[iid], review_ids=[rid])
    _run(case())


def test_rollback_linked_promoted_invalidates_evidence():
    async def case():
        async with AsyncSessionLocal() as s:
            tid, iid, target, rid, eid, pid = await _linked_promoted_fixture(s)
            try:
                before = (
                    await s.execute(
                        text("SELECT confidence FROM mirror_region_connections WHERE id=:t"),
                        {"t": target},
                    )
                ).scalar_one()
                result = await pes.rollback_review_for_rescore(
                    s, uuid.UUID(rid), reason="证据有误", actor="reviewer-1"
                )
                assert result["promotion_rollback"] == "completed"
                # evidence invalidated(不物理删除)+ 置信度回算
                ev = (
                    await s.execute(
                        text("SELECT verification_status FROM mirror_evidence_records WHERE id=:e"),
                        {"e": eid},
                    )
                ).scalar_one()
                assert ev == "invalidated"
                log = (
                    await s.execute(
                        text("SELECT status FROM confidence_adjustment_logs WHERE evidence_id=:e"),
                        {"e": eid},
                    )
                ).scalar_one()
                assert log == "rolled_back"
                after = (
                    await s.execute(
                        text("SELECT confidence FROM mirror_region_connections WHERE id=:t"),
                        {"t": target},
                    )
                ).scalar_one()
                assert before is not None and (after is None or after <= before)
                # 旧 review 仍 approved+promoted(历史事实),仅 superseded
                row = await _review_row(s, rid)
                assert row["review_status"] == "approved"
                assert row["promotion_status"] == "promoted"
                assert row["superseded_at"] is not None
                # 派生有效晋升状态 = rolled_back
                eff = await pes._derive_effective_promotion_status(s, row)
                assert eff == "rolled_back"
            finally:
                await _cleanup(
                    s, task_ids=[tid], item_ids=[iid], review_ids=[rid],
                    evidence_ids=[eid], target_ids=[target], paper_ids=[pid],
                )
    _run(case())


def test_rollback_failure_rolls_back_everything():
    async def case():
        async with AsyncSessionLocal() as s:
            tid, iid, target, rid, eid, pid = await _linked_promoted_fixture(s)
            orig = pes._invalidate_evidence_inplace

            async def boom(_session, _eid, *, reason, operator_id=None):
                raise ValueError("evidence boom")

            try:
                pes._invalidate_evidence_inplace = boom
                with pytest.raises(pes.EvidenceReviewError, match="promotion rollback failed") as ei:
                    await pes.rollback_review_for_rescore(
                        s, uuid.UUID(rid), reason="x", actor="reviewer-1"
                    )
                await s.rollback()
                row = await _review_row(s, rid)
                assert row["superseded_at"] is None
                item = await _item_row(s, iid)
                assert item["status"] == "completed"
                assert item["rescore_source_review_id"] is None
                ev = (
                    await s.execute(
                        text("SELECT verification_status FROM mirror_evidence_records WHERE id=:e"),
                        {"e": eid},
                    )
                ).scalar_one()
                assert ev != "invalidated"
            finally:
                pes._invalidate_evidence_inplace = orig
                await _cleanup(
                    s, task_ids=[tid], item_ids=[iid], review_ids=[rid],
                    evidence_ids=[eid], target_ids=[target], paper_ids=[pid],
                )
    _run(case())


def test_duplicate_rollback_conflicts():
    async def case():
        async with AsyncSessionLocal() as s:
            tid, iid, target, rid = await _linked_approved_fixture(s)
            try:
                await pes.rollback_review_for_rescore(s, uuid.UUID(rid), reason="第一次", actor="a")
                with pytest.raises(pes.ReviewConflictError, match="already been superseded") as ei:
                    await pes.rollback_review_for_rescore(s, uuid.UUID(rid), reason="第二次", actor="b")
                assert ei.value.code == "REVIEW_ALREADY_SUPERSEDED"
            finally:
                await _cleanup(s, task_ids=[tid], item_ids=[iid], review_ids=[rid])
    _run(case())


def test_concurrent_rollback_only_one_succeeds():
    """双 session 并发回退:review 行锁串行化,恰好一个成功、一个 409,只产生一个重评分支。"""

    async def main():
        async with AsyncSessionLocal() as s:
            tid, iid, target, rid = await _linked_approved_fixture(s)
        results: dict[str, dict] = {}
        errors: dict[str, Exception] = {}

        async def worker(name: str):
            async with AsyncSessionLocal() as s:
                try:
                    results[name] = await pes.rollback_review_for_rescore(
                        s, uuid.UUID(rid), reason=f"并发-{name}", actor=name
                    )
                except Exception as exc:  # noqa: BLE001
                    errors[name] = exc

        await asyncio.gather(worker("w1"), worker("w2"))
        assert len(results) == 1 and len(errors) == 1
        failed = next(iter(errors.values()))
        assert isinstance(failed, pes.ReviewConflictError)
        assert failed.code == "REVIEW_ALREADY_SUPERSEDED"
        # 只产生一个重评分支:item 上下文唯一,无后继 review
        async with AsyncSessionLocal() as s:
            item = await _item_row(s, iid)
            assert item["rescore_source_review_id"] == uuid.UUID(rid)
            n = (
                await s.execute(
                    text("SELECT COUNT(*) FROM paper_evidence_reviews WHERE supersedes_review_id=:r"),
                    {"r": rid},
                )
            ).scalar_one()
            assert n == 0
            await _cleanup(s, task_ids=[tid], item_ids=[iid], review_ids=[rid])

    _run(main())


def test_rollback_reason_required():
    async def case():
        async with AsyncSessionLocal() as s:
            tid, iid, target, rid = await _linked_approved_fixture(s)
            try:
                for bad in (None, "", "   "):
                    with pytest.raises(pes.EvidenceReviewError) as ei:
                        await pes.rollback_review_for_rescore(s, uuid.UUID(rid), reason=bad)
                    assert ei.value.code == "ROLLBACK_REASON_REQUIRED"
            finally:
                await _cleanup(s, task_ids=[tid], item_ids=[iid], review_ids=[rid])
    _run(case())


def test_rejected_review_not_rollbackable():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            target = str(uuid.uuid4())
            iid = await _add_item(s, tid, target)
            r = await _build(s, task_id=tid, task_item_id=iid, target_id=target, direction="not_found")
            try:
                can, block = await pes._review_rollback_capability(s, await _review_row(s, r["review_id"]))
                assert (can, block) == (False, "REJECTED")
                with pytest.raises(pes.ReviewConflictError, match="only approved") as ei:
                    await pes.rollback_review_for_rescore(s, uuid.UUID(r["review_id"]), reason="x")
                assert ei.value.code == "REVIEW_NOT_ROLLBACKABLE"
            finally:
                await _cleanup(s, task_ids=[tid], item_ids=[iid], review_ids=[r["review_id"]])
    _run(case())


# ════════════════════════════════════════════════════════════════════════════
# 3. standalone / legacy / orphan
# ════════════════════════════════════════════════════════════════════════════


async def _insert_standalone_approved(session, target_id: str, *, task_id=None) -> str:
    rid = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO paper_evidence_reviews "
            "(id, target_type, target_id, task_id, review_status, promotion_status, "
            "revision_no, reviewed_at, approved_at, reviewer_direction, reviewer_confidence, "
            "claim_version, claim_text_snapshot) "
            "VALUES (:id, 'connection', :tgt, :task, 'approved', 'not_ready', 1, now(), now(), "
            "'supports', 0.7, 'v1', 'claim')"
        ),
        {"id": rid, "tgt": target_id, "task": task_id},
    )
    await session.commit()
    return rid


def test_standalone_rollback_creates_single_object_task():
    async def case():
        async with AsyncSessionLocal() as s:
            target = str(uuid.uuid4())
            await _make_connection(s, target, confidence=0.42)
            rid = await _insert_standalone_approved(s, target)
            new_tid: str | None = None
            new_iid: str | None = None
            try:
                result = await pes.rollback_review_for_rescore(
                    s, uuid.UUID(rid), reason="重新评分", actor="reviewer-1"
                )
                new_tid = result["navigation"]["task_id"]
                new_iid = result["navigation"]["task_item_id"]
                assert new_tid is not None and new_iid is not None
                t = (
                    await s.execute(
                        text("SELECT * FROM paper_evidence_tasks WHERE id=:t"), {"t": new_tid}
                    )
                ).first()
                tm = dict(t._mapping)
                assert tm["scope"] == "single_object"
                assert tm["name"].startswith("重新评分")
                assert tm["filter_snapshot"] == {"rescore_of": rid}
                item = await _item_row(s, new_iid)
                assert item["status"] == "awaiting_review"
                assert item["rescore_source_review_id"] == uuid.UUID(rid)
                assert item["rescore_revision_no"] == 2
                assert float(item["current_confidence"]) == 0.42
                # 旧 review 未伪造 task_id
                row = await _review_row(s, rid)
                assert row["task_id"] is None and row["superseded_at"] is not None
            finally:
                await _cleanup(
                    s,
                    task_ids=[new_tid] if new_tid else [],
                    item_ids=[new_iid] if new_iid else [],
                    review_ids=[rid],
                    target_ids=[target],
                )
    _run(case())


def test_legacy_unique_match_rollback():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            target = str(uuid.uuid4())
            iid = await _add_item(s, tid, target, status="completed")
            rid = await _insert_standalone_approved(s, target, task_id=tid)
            try:
                result = await pes.rollback_review_for_rescore(
                    s, uuid.UUID(rid), reason="legacy 重评", actor="a"
                )
                assert result["navigation"]["task_item_id"] == iid
                # 旧 review 历史 task 字段未被改写
                row = await _review_row(s, rid)
                assert row["task_item_id"] is None and row["task_id"] == uuid.UUID(tid)
                item = await _item_row(s, iid)
                assert item["status"] == "awaiting_review"
                assert item["rescore_source_review_id"] == uuid.UUID(rid)
            finally:
                await _cleanup(s, task_ids=[tid], item_ids=[iid], review_ids=[rid])
    _run(case())


def test_legacy_zero_match_blocked():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            target = str(uuid.uuid4())
            rid = await _insert_standalone_approved(s, target, task_id=tid)
            try:
                can, block = await pes._review_rollback_capability(s, await _review_row(s, rid))
                assert (can, block) == (False, "NO_TASK_ITEM")
                with pytest.raises(pes.ReviewConflictError) as ei:
                    await pes.rollback_review_for_rescore(s, uuid.UUID(rid), reason="x")
                assert ei.value.code == "NO_TASK_ITEM"
            finally:
                await _cleanup(s, task_ids=[tid], review_ids=[rid])
    _run(case())


def test_legacy_ambiguous_blocked():
    """同任务同 target 多 item 被唯一索引阻止,以 mock 查询结果单测歧义分支。"""
    async def case():
        session = AsyncMock()
        locked_res = MagicMock()
        locked_res.first.return_value = MagicMock(
            _mapping={
                "id": uuid.uuid4(), "target_type": "connection", "target_id": uuid.uuid4(),
                "task_id": uuid.uuid4(), "task_item_id": None, "review_status": "approved",
                "promotion_status": "not_ready", "evidence_id": None, "revision_no": 1,
                "superseded_at": None,
            }
        )
        peers_res = MagicMock()
        peers_res.scalar_one.return_value = 1  # 唯一链尾,通过歧义校验
        matches_res = MagicMock()
        matches_res.all.return_value = [(uuid.uuid4(), "pending"), (uuid.uuid4(), "pending")]
        session.execute = AsyncMock(side_effect=[locked_res, peers_res, matches_res])
        with pytest.raises(pes.ReviewConflictError) as ei:
            await pes.rollback_review_for_rescore(session, uuid.uuid4(), reason="x")
        assert ei.value.code == "AMBIGUOUS_TASK_ITEM"
    _run(case())


def test_orphan_task_item_blocked():
    async def case():
        async with AsyncSessionLocal() as s:
            target = str(uuid.uuid4())
            rid = str(uuid.uuid4())
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_reviews "
                    "(id, target_type, target_id, task_item_id, review_status, promotion_status, "
                    "reviewed_at, approved_at, reviewer_confidence) "
                    "VALUES (:id, 'connection', :tgt, :iid, 'approved', 'not_ready', now(), now(), 0.7)"
                ),
                {"id": rid, "tgt": target, "iid": str(uuid.uuid4())},
            )
            await s.commit()
            try:
                can, block = await pes._review_rollback_capability(s, await _review_row(s, rid))
                assert (can, block) == (False, "ORPHAN_TASK_CONTEXT")
                with pytest.raises(pes.ReviewConflictError) as ei:
                    await pes.rollback_review_for_rescore(s, uuid.UUID(rid), reason="x")
                assert ei.value.code == "ORPHAN_TASK_CONTEXT"
            finally:
                await _cleanup(s, review_ids=[rid])
    _run(case())


def test_cancelled_task_blocked():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s, raw_status="cancelled")
            target = str(uuid.uuid4())
            iid = await _add_item(s, tid, target, status="completed")
            rid = await _insert_standalone_approved(s, target, task_id=tid)
            try:
                can, block = await pes._review_rollback_capability(s, await _review_row(s, rid))
                assert (can, block) == (False, "TASK_CANCELLED")
            finally:
                await _cleanup(s, task_ids=[tid], item_ids=[iid], review_ids=[rid])
    _run(case())


# ════════════════════════════════════════════════════════════════════════════
# 4. build 新版本挂链 / 历史 / capability
# ════════════════════════════════════════════════════════════════════════════


def test_build_after_rollback_links_new_version():
    async def case():
        async with AsyncSessionLocal() as s:
            tid, iid, target, rid = await _linked_approved_fixture(s)
            try:
                await pes.rollback_review_for_rescore(s, uuid.UUID(rid), reason="重评", actor="a")
                r2 = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                row2 = await _review_row(s, r2["review_id"])
                assert row2["revision_no"] == 2
                assert row2["supersedes_review_id"] == uuid.UUID(rid)
                # 新评分是本次数据,非复制旧评分
                assert row2["reviewer_confidence"] == 0.7
                # 20) 上下文已清
                item = await _item_row(s, iid)
                assert item["rescore_source_review_id"] is None and item["rescore_revision_no"] is None
                # 22) approve 新版本 → 链尾 current
                await pes.approve_review(s, uuid.UUID(r2["review_id"]), operator_id="reviewer-1")
                dto_old = await pes._review_row_to_dict(s, await _review_row(s, rid))
                dto_new = await pes._review_row_to_dict(s, await _review_row(s, r2["review_id"]))
                assert dto_old["is_current"] is False and dto_new["is_current"] is True
                assert dto_old["can_rollback_rescore"] is False
                assert dto_new["can_rollback_rescore"] is True
                item2 = await _item_row(s, iid)
                assert item2["status"] == "completed"
            finally:
                await _cleanup(s, task_ids=[tid], item_ids=[iid], review_ids=[rid, r2["review_id"]])
    _run(case())


def test_build_failure_keeps_rescore_context():
    async def case():
        async with AsyncSessionLocal() as s:
            tid, iid, target, rid = await _linked_approved_fixture(s)
            try:
                await pes.rollback_review_for_rescore(s, uuid.UUID(rid), reason="重评", actor="a")
                # 模拟链已前进(伪造后继)→ build 冲突,上下文保留
                fake_child = str(uuid.uuid4())
                await s.execute(
                    text(
                        "INSERT INTO paper_evidence_reviews "
                        "(id, target_type, target_id, review_status, promotion_status, "
                        "revision_no, supersedes_review_id, reviewed_at, reviewer_confidence) "
                        "VALUES (:id, 'connection', :tgt, 'approved', 'not_ready', 2, :src, now(), 0.6)"
                    ),
                    {"id": fake_child, "tgt": target, "src": rid},
                )
                await s.commit()
                with pytest.raises(pes.ReviewConflictError, match="rescore chain already advanced"):
                    await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                item = await _item_row(s, iid)
                assert item["rescore_source_review_id"] == uuid.UUID(rid)
                assert item["rescore_revision_no"] == 2
            finally:
                await _cleanup(
                    s, task_ids=[tid], item_ids=[iid], review_ids=[rid, fake_child]
                )
    _run(case())


def test_history_chain_only_includes_chain_members():
    async def case():
        async with AsyncSessionLocal() as s:
            tid, iid, target, rid = await _linked_approved_fixture(s)
            other_tid: str | None = None
            other_r: str | None = None
            try:
                await pes.rollback_review_for_rescore(s, uuid.UUID(rid), reason="重评", actor="a")
                r2 = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                # 同 target 的另一任务 review(不得串入历史;直接插 approved review,
                # 不建 active item —— 全局唯一索引 uq_evidence_task_item_active_target 阻止同 target 第二个 active item)
                other_tid = await _make_task(s)
                other_r = await _insert_standalone_approved(s, target, task_id=other_tid)
                hist = await pes.get_review_history(s, uuid.UUID(r2["review_id"]))
                ids = [h["review_id"] for h in hist["items"]]
                assert ids == [rid, r2["review_id"]]
                v2 = next(h for h in hist["items"] if h["review_id"] == r2["review_id"])
                assert v2["revision_no"] == 2 and v2["is_current"] is True
                v1 = next(h for h in hist["items"] if h["review_id"] == rid)
                assert v1["rollback_reason"] == "重评"
            finally:
                await _cleanup(
                    s, task_ids=[tid, other_tid] if other_tid else [tid], item_ids=[iid],
                    review_ids=[rid, r2["review_id"]] + ([other_r] if other_r else []),
                )
    _run(case())


def test_effective_promotion_status_derived():
    async def case():
        async with AsyncSessionLocal() as s:
            tid, iid, target, rid, eid, pid = await _linked_promoted_fixture(s)
            try:
                row = await _review_row(s, rid)
                assert await pes._derive_effective_promotion_status(s, row) == "active"
                await pes.rollback_review_for_rescore(s, uuid.UUID(rid), reason="x", actor="a")
                assert await pes._derive_effective_promotion_status(s, await _review_row(s, rid)) == "rolled_back"
                # not_promoted
                rid2 = await _insert_standalone_approved(s, str(uuid.uuid4()))
                try:
                    assert await pes._derive_effective_promotion_status(s, await _review_row(s, rid2)) == "not_promoted"
                finally:
                    await _cleanup(s, review_ids=[rid2])
            finally:
                await _cleanup(
                    s, task_ids=[tid], item_ids=[iid], review_ids=[rid],
                    evidence_ids=[eid], target_ids=[target], paper_ids=[pid],
                )
    _run(case())


# ════════════════════════════════════════════════════════════════════════════
# 5. API 级:权限(403)
# ════════════════════════════════════════════════════════════════════════════


def test_ambiguous_history_multiple_chain_tails_blocked():
    """S8:同 task item 两条 approved、revision_no=1、无 supersedes/superseded 链 → 双方 capability=false + 端点 409。"""
    async def case():
        async with AsyncSessionLocal() as s:
            tid, iid, target, r1 = await _linked_approved_fixture(s)
            # 手动构造第二条无链终态 review(同一 item;绕过防重,模拟历史脏数据)
            rid2 = str(uuid.uuid4())
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_reviews "
                    "(id, target_type, target_id, task_id, task_item_id, review_status, "
                    "promotion_status, revision_no, reviewed_at, approved_at, reviewer_confidence) "
                    "VALUES (:id, 'connection', :tgt, :tid, :iid, 'approved', 'not_ready', 1, "
                    "now(), now(), 0.6)"
                ),
                {"id": rid2, "tgt": target, "tid": tid, "iid": iid},
            )
            await s.commit()
            try:
                row1 = await _review_row(s, r1)
                row2 = await _review_row(s, rid2)
                assert row1["revision_no"] == 1 and row1["supersedes_review_id"] is None and row1["superseded_at"] is None
                assert row2["revision_no"] == 1 and row2["supersedes_review_id"] is None and row2["superseded_at"] is None
                can1, block1 = await pes._review_rollback_capability(s, row1)
                can2, block2 = await pes._review_rollback_capability(s, row2)
                assert (can1, block1) == (False, "AMBIGUOUS_REVIEW_HISTORY")
                assert (can2, block2) == (False, "AMBIGUOUS_REVIEW_HISTORY")
                # 端点级二次校验:不能只依赖列表 capability
                with pytest.raises(pes.ReviewConflictError) as ei:
                    await pes.rollback_review_for_rescore(s, uuid.UUID(r1), reason="x")
                assert ei.value.code == "AMBIGUOUS_REVIEW_HISTORY"
                with pytest.raises(pes.ReviewConflictError) as ei2:
                    await pes.rollback_review_for_rescore(s, uuid.UUID(rid2), reason="x")
                assert ei2.value.code == "AMBIGUOUS_REVIEW_HISTORY"
                # 两条无链 review 的 history 各自独立,不假装成同一有序链
                h1 = await pes.get_review_history(s, uuid.UUID(r1))
                h2 = await pes.get_review_history(s, uuid.UUID(rid2))
                assert [x["review_id"] for x in h1["items"]] == [r1]
                assert [x["review_id"] for x in h2["items"]] == [rid2]
            finally:
                await _cleanup(
                    s, task_ids=[tid], item_ids=[iid], review_ids=[r1, rid2]
                )
    _run(case())


def test_history_cycle_defense():
    """S8:损坏数据 A↔B supersedes 循环不得无限递归。"""
    async def case():
        async with AsyncSessionLocal() as s:
            ra = str(uuid.uuid4())
            rb = str(uuid.uuid4())
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_reviews "
                    "(id, target_type, target_id, review_status, promotion_status, "
                    "revision_no, reviewed_at, reviewer_confidence) "
                    "VALUES (:id, 'connection', :tgt, 'approved', 'not_ready', 1, now(), 0.6)"
                ),
                {"id": ra, "tgt": str(uuid.uuid4())},
            )
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_reviews "
                    "(id, target_type, target_id, review_status, promotion_status, "
                    "revision_no, supersedes_review_id, reviewed_at, reviewer_confidence) "
                    "VALUES (:id, 'connection', :tgt, 'approved', 'not_ready', 2, :sup, now(), 0.6)"
                ),
                {"id": rb, "tgt": str(uuid.uuid4()), "sup": ra},
            )
            # 形成循环:ra.supersedes = rb
            await s.execute(
                text("UPDATE paper_evidence_reviews SET supersedes_review_id=:sup WHERE id=:id"),
                {"id": ra, "sup": rb},
            )
            await s.commit()
            try:
                hist = await pes.get_review_history(s, uuid.UUID(ra))
                # 防环:链长有界,不无限递归
                assert 1 <= len(hist["items"]) <= 2
            finally:
                # 先断环再清理
                await s.execute(
                    text("UPDATE paper_evidence_reviews SET supersedes_review_id=NULL WHERE id=:id"),
                    {"id": ra},
                )
                await _cleanup(s, review_ids=[ra, rb])
    _run(case())


def test_capability_respects_viewer_role(monkeypatch):
    """S8:viewer 角色的 list/detail capability 一律 false+FORBIDDEN;有权限角色得到真实 capability。"""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    import app.routers.ontology as onto_router
    from app.main import app

    async def fixture():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            target = str(uuid.uuid4())
            iid = await _add_item(s, tid, target)
            r = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
            await pes.approve_review(s, uuid.UUID(r["review_id"]), operator_id="a")
            return tid, iid, target, r["review_id"]

    tid, iid, target, rid = _run(fixture())
    try:
        client = TestClient(app, raise_server_exceptions=False)
        # viewer → FORBIDDEN capability(真实 reviewer role 的默认 admin 与 viewer 对比)
        monkeypatch.setattr(onto_router, "get_settings", lambda: SimpleNamespace(ontology_role="viewer"))
        resp = client.get(f"/api/ontology/evidence/reviews/{rid}")
        body = resp.json()
        assert body["can_rollback_rescore"] is False
        assert body["rollback_block_reason"] == "FORBIDDEN"
        resp_list = client.get("/api/ontology/evidence/reviews?page_size=50")
        for item in resp_list.json()["items"]:
            assert item["can_rollback_rescore"] is False
            assert item["rollback_block_reason"] == "FORBIDDEN"
        # 有权限角色 → 真实 capability(linked approved 唯一链尾 → true)
        monkeypatch.setattr(onto_router, "get_settings", lambda: SimpleNamespace(ontology_role="reviewer"))
        resp2 = client.get(f"/api/ontology/evidence/reviews/{rid}")
        assert resp2.json()["can_rollback_rescore"] is True
        assert resp2.json()["rollback_block_reason"] is None
        # 绕过前端直接调端点 → viewer 403
        monkeypatch.setattr(onto_router, "get_settings", lambda: SimpleNamespace(ontology_role="viewer"))
        resp3 = client.post(
            f"/api/ontology/evidence/reviews/{rid}/rollback-for-rescore", json={"reason": "x"}
        )
        assert resp3.status_code == 403
    finally:
        _run(_cleanup_sync(tid, iid, rid))


async def _cleanup_sync(tid, iid, rid):
    async with AsyncSessionLocal() as s:
        await _cleanup(s, task_ids=[tid], item_ids=[iid], review_ids=[rid])


def test_rollback_endpoint_requires_reviewer_role(monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    import app.routers.ontology as onto_router
    from app.main import app

    # 强制 viewer 角色(默认配置为 ontology_admin,须显式降级以验证权限拒绝)
    monkeypatch.setattr(
        onto_router, "get_settings", lambda: SimpleNamespace(ontology_role="viewer")
    )
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/api/ontology/evidence/reviews/{uuid.uuid4()}/rollback-for-rescore",
        json={"reason": "x"},
    )
    # viewer role → 403 结构化
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["code"] == "FORBIDDEN"
