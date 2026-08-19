# NN Final Fix Report — 非神经靶标治理收尾修复

Date: 2026-08-19
Branch: `codex/ontology-evidence`
Scope: 全分支终审的 2 个 Important 发现(F1 / F2)修复。

## F1:批量物化路径补靶标分类

**问题**:`materialize_task_items_background` 的 item 插入(`_materialize_page` 内 per-target 循环,原 5694 行处)未调用 `_classify_item_target`,批量 scope 任务的非神经靶标(脑室/脑脊液/脑膜等)不会落 `non_neural_target` 标记,会跑完整论文检索。

**修复**(`backend/app/services/paper_evidence_service.py` `_materialize_page`):
- 循环内对每个 insert 目标调用已存在的 `_classify_item_target(session, target_type, oid_uuid)`:
  ```python
  target_kind = await _classify_item_target(session, target_type, oid_uuid)
  po = "non_neural_target" if target_kind == "non_neural" else None
  ```
- INSERT 增加 `preprocess_outcome` 列与 `:po` 参数(`SELECT ... , 'pending', :po`)。
- 镜像行缺失时 `_classify_item_target` 内部回退 `unknown` → `po=None` → 列写 NULL,与 label 快照回退行为一致,不误标。

**测试**(`backend/tests/test_paper_evidence_live_fields.py`):
- 新增 `test_materialize_classifies_non_neural_target`:镜像连接 target_region_name_cn=「侧脑室」→ 物化后 item 的 `preprocess_outcome='non_neural_target'`,label/confidence 快照正常。
- 强化 `test_materialize_missing_row_falls_back_to_target_id`:追加断言镜像行缺失时 `preprocess_outcome IS NULL`(回退 unknown 行为不变)。

## F2:evidence_negated 需方向为 contradicts

**问题**:`_process_batch_item_v2` 的 outcome 赋值处(5348 行)把「否定向检索 + 有已核验片段」一律标 `evidence_negated`,即使提取方向为 supports(命中论文实际支持该连接)也会被误标为证据否定。

**修复**(`backend/app/services/paper_evidence_service.py` `_process_batch_item_v2`):
```python
preprocess_outcome = (
    "evidence_negated"
    if query_is_negative and verified_any
    and (candidates[0].get("model_direction") == "contradicts")
    else "evidence_found" if verified_any else "no_evidence_found"
),
```
`verified_any` 为真时 candidates 必非空(verified passage 必来自某 candidate),`candidates[0]` 安全;`_save_item_candidates` 已先行写入,`model_direction` 取自 `extraction.overall_direction`。

**测试**(`backend/tests/test_paper_evidence_batch.py`):
- 现有 `test_negative_round_marks_evidence_negated`(方向 contradicts)→ 仍标 `evidence_negated`,保持绿色。
- 新增 `test_negative_round_supports_direction_not_marked_negated`:否定向检索命中 + 提取方向 supports(已核验)→ `preprocess_outcome='evidence_found'`,不被误标否定。
- `_cleanup_batch_paper` 参数化 pmid(默认 '10001'),新用例用 '10002' 清理。

## 测试结果

```
pytest tests/test_paper_evidence_batch.py tests/test_paper_evidence_live_fields.py \
       tests/test_paper_evidence_batch_scale.py tests/test_mirror_promotion_to_final.py -q
→ 57 passed (含新增 2 例 + 强化 1 例)
```

## 涉及文件

- `backend/app/services/paper_evidence_service.py`(两处修复)
- `backend/tests/test_paper_evidence_batch.py`(F2 负向用例 + cleanup 参数化)
- `backend/tests/test_paper_evidence_live_fields.py`(F1 物化用例 + 缺失回退断言)
