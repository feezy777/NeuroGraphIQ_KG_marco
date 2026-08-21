# Task 1: 后端回退端点（reopen）

来源：`docs/superpowers/plans/2026-08-13-evidence-tasks-page-redesign.md` Task 1（BASE: 2a0259b）

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`（在 `complete_batch_item_reviewed` 之后插入新函数）
- Modify: `backend/app/routers/ontology.py`（在 `/evidence/batch/{task_id}/items/{item_id}/reviewed` 端点之后插入新端点）
- Test: `backend/tests/test_paper_evidence_batch_phase4.py`（文件末尾追加 3 个测试）

**Interfaces:**
- Produces: `pes.reopen_batch_item(session, task_id, item_id) -> dict`（`{"task_id", "item_id", "status": "awaiting_review"}`；不存在 → `ValueError("task item not found")`；非 completed → `ValueError("item is not completed")`）。路由 `POST /api/ontology/evidence/batch/{task_id}/items/{item_id}/reopen`，`require_role("reviewer")`，ValueError → 400 `INVALID_REQUEST`。

## Steps

### Step 1: 写失败测试

在 `backend/tests/test_paper_evidence_batch_phase4.py` 末尾追加（该文件已有 `_run/_make_task/_run_task/_cleanup`、`pytest`、`uuid`、`text`、`AsyncSessionLocal`、`pes` 的 import）：

```python
def test_reopen_completed_item_returns_to_awaiting_review():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        _run(_run_task(task_id))
        async def case():
            async with AsyncSessionLocal() as s:
                item_id = (
                    await s.execute(
                        text("SELECT id::text FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                        {"tid": task_id},
                    )
                ).scalar_one()
                await pes.complete_batch_item_reviewed(
                    s, task_id, item_id, evidence_id=str(uuid.uuid4()), operator_id="reviewer-1"
                )
                result = await pes.reopen_batch_item(s, task_id, item_id)
                assert result["status"] == "awaiting_review"
                row = (
                    await s.execute(
                        text(
                            "SELECT status, evidence_id IS NULL, reviewed_at IS NULL, reviewed_by IS NULL "
                            "FROM paper_evidence_task_items WHERE id::text=:iid"
                        ),
                        {"iid": item_id},
                    )
                ).first()
                assert row[0] == "awaiting_review"
                assert row[1] is True
                assert row[2] is True
                assert row[3] is True
                st = (
                    await s.execute(
                        text("SELECT review_status FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": task_id},
                    )
                ).first()
                assert st[0] == "in_review"
        _run(case())
    finally:
        _run(_cleanup(task_id))


def test_reopen_non_completed_item_raises():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        async def case():
            async with AsyncSessionLocal() as s:
                item_id = (
                    await s.execute(
                        text("SELECT id::text FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                        {"tid": task_id},
                    )
                ).scalar_one()
                with pytest.raises(ValueError, match="item is not completed"):
                    await pes.reopen_batch_item(s, task_id, item_id)
        _run(case())
    finally:
        _run(_cleanup(task_id))


def test_reopen_missing_item_raises():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        async def case():
            async with AsyncSessionLocal() as s:
                with pytest.raises(ValueError, match="task item not found"):
                    await pes.reopen_batch_item(s, task_id, str(uuid.uuid4()))
        _run(case())
    finally:
        _run(_cleanup(task_id))
```

### Step 2: 运行测试确认失败

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch_phase4.py -k reopen -v`
Expected: FAIL —— `AttributeError: module 'app.services.paper_evidence_service' has no attribute 'reopen_batch_item'`

### Step 3: 实现 service 函数

在 `backend/app/services/paper_evidence_service.py` 的 `complete_batch_item_reviewed` 函数之后（约 3908 行）插入：

```python
async def reopen_batch_item(
    session: AsyncSession,
    task_id: str,
    item_id: str,
) -> dict:
    """将已完成(completed)的任务项回退为待审核(awaiting_review),支持重新审查。

    仅回退 item 状态与已记录的证据关联;已写入 paper_evidence 的记录不撤销(留痕),
    重新审核晋升时按现有流程产生新记录。
    """
    exists = (
        await session.execute(
            text(
                "SELECT 1 FROM paper_evidence_task_items "
                "WHERE task_id::text=:tid AND id::text=:iid"
            ),
            {"tid": task_id, "iid": item_id},
        )
    ).first()
    if exists is None:
        raise ValueError("task item not found")
    result = await session.execute(
        text(
            "UPDATE paper_evidence_task_items SET status='awaiting_review', reviewed_by=NULL, "
            "reviewed_at=NULL, evidence_id=NULL, updated_at=now() "
            "WHERE task_id::text=:tid AND id::text=:iid AND status='completed'"
        ),
        {"tid": task_id, "iid": item_id},
    )
    await session.commit()
    if result.rowcount == 0:
        raise ValueError("item is not completed")
    await _update_task_totals(session, task_id)
    await session.commit()
    await _update_task_review_status(session, task_id)
    await session.commit()
    return {"task_id": task_id, "item_id": item_id, "status": "awaiting_review"}
```

### Step 4: 实现路由端点

在 `backend/app/routers/ontology.py` 的 `paper_evidence_batch_item_reviewed` 端点之后（约 1133 行）插入：

```python
@router.post("/evidence/batch/{task_id}/items/{item_id}/reopen")
async def paper_evidence_batch_item_reopen(
    task_id: str,
    item_id: str,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        return await pes.reopen_batch_item(session, task_id, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})
```

### Step 5: 运行测试确认通过

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch_phase4.py -k reopen -v`
Expected: PASS —— 3 passed

### Step 6: 提交

```bash
git add backend/app/services/paper_evidence_service.py backend/app/routers/ontology.py backend/tests/test_paper_evidence_batch_phase4.py
git commit -m "feat(evidence): 任务项回退端点 reopen(completed→awaiting_review,清 reviewed 字段)"
```

## 硬约束

- 只允许改动上述 3 个文件。工作树中有大量其他未提交改动，**绝不可 `git add -A` / `git add .`**，提交必须按上面列出的精确路径。
- 不要改其他任何文件；不要动前端。
- 后端测试需要本机 PostgreSQL 已启动（.env 配置）；若 DB 连接失败，报告 BLOCKED 并附错误。
- 提交消息不加 Co-Authored-By。
