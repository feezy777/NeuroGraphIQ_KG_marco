# Task 5 Report: 晋升跳过治理边(非神经靶标/证据否定边永久跳过晋升)

## 定位到的晋升入口

- **文件**: `backend/app/services/mirror_promotion_service.py`
- **判定点**: `validate_promotion_eligibility(session, target_type, obj)`(第 ~311 行起)—— 这是 preview(`build_promotion_preview_item`)与 run(`run_mirror_promotion` 主循环)共用的唯一晋升判定函数。返回 `(eligible, reason, review_id, val_summary)`;run 循环对 ineligible 目标创建 `skipped_ineligible` promotion record(message=reason)、不写 final 行、不改对象状态 —— 天然满足 brief 的「跳过、不写 final、不改变状态、标记跳过原因」意图。
- **数据来源**: `preprocess_outcome` 不在 mirror ORM 对象上,而在 raw-SQL 表 `paper_evidence_task_items`(migration `20260807_paper_evidence_v8.sql` 第 22 行),按 `(target_type, target_id)` 关联 mirror 对象。evidence task 的 target_type 取值来自 `backend/app/services/evidence_target_adapter.py` 的 `TARGET_MODELS`(`connection`/`projection`、`region_function`、`circuit`、`circuit_function`、`circuit_step`、`projection_function`),与晋升 target_type(`connection`/`function`/`circuit`/`triple`)不同。

## 实现(TDD)

### Step 2 RED — 先写失败测试

在 `backend/tests/test_mirror_promotion_to_final.py`(既有 23 例,全部 AsyncMock 模式)追加 7 例:

| 用例 | 断言 |
|------|------|
| `test_non_neural_target_ineligible_never_promote` | outcome=`non_neural_target` → ineligible, reason=`GOVERNANCE_SKIP_NEVER_PROMOTE` |
| `test_evidence_negated_ineligible_never_promote` | outcome=`evidence_negated`(function 类型,走 `region_function` 映射)→ 同上 |
| `test_no_evidence_found_does_not_block_promotion` | outcome=`no_evidence_found` → eligible |
| `test_evidence_found_does_not_block_promotion` | outcome=`evidence_found` → eligible |
| `test_no_evidence_task_item_does_not_block_promotion` | 无 task item(查询返回 None)→ eligible |
| `test_run_skips_non_neural_target_no_final_row` | 端到端 run:有 review 的 `non_neural_target` 连接 → promoted=0, skipped_ineligible=1, promotion record message=`GOVERNANCE_SKIP_NEVER_PROMOTE`,对象 promotion_status 保持 `not_promoted`,`promote_connection` 不得被调用 |
| `test_run_promotes_evidence_found_control` | 对照组:outcome=`evidence_found` 正常 run → promoted=1,对象 promotion_status=`promoted` |

RED 证据:实现前 `3 failed, 4 passed`(3 个治理跳过用例失败;对照组全过)。

### Step 3 GREEN — 实现

`backend/app/services/mirror_promotion_service.py`:

1. 常量:`GOVERNANCE_SKIP_NEVER_PROMOTE = "GOVERNANCE_SKIP_NEVER_PROMOTE"`、`GOVERNANCE_SKIP_OUTCOMES = frozenset({"non_neural_target", "evidence_negated"})`、`EVIDENCE_TASK_TARGET_TYPES`(connection→`connection`/`projection`,function→`region_function`,circuit→`circuit`;triple 无证据任务支持 → 不查)。
2. 新增 `get_governance_skip_outcome(session, target_type, target_id)`:raw SQL 查 `paper_evidence_task_items` 最新(created_at DESC LIMIT 1)一条的 `preprocess_outcome`,命中治理集合则返回 outcome,否则 None(含无 task item)。
3. `validate_promotion_eligibility` 中在 `detect_final_duplicate` 之前插入:
   ```python
   governance_outcome = await get_governance_skip_outcome(session, target_type, obj.id)
   if governance_outcome is not None:
       return False, GOVERNANCE_SKIP_NEVER_PROMOTE, approve_record.id, val_summary
   ```
   放置在该位置的理由:(a) 治理边即使有 review 也跳过(review 通过与否不影响语义——不 approved 本就 ineligible);(b) 治理原因优先于重复检测;(c) 不影响既有测试的 `session.execute` side_effect 编排(早退用例不触及;`test_warning_does_not_block` 的副作用序列恰好兼容)。

### Step 4 回归确认

- `tests/test_mirror_promotion_to_final.py`:30 passed(23 既有 + 7 新增)
- `tests/ -k promotion`:81 passed(含 `test_promotion.py`、`test_final_macro_clinical_promotion.py`)
- 相邻镜像回归(`test_mirror_review_queue`、`test_mirror_kg_schema`、`test_mirror_rule_validation`、`test_promotion`、`test_final_macro_clinical_promotion`):93 passed

## Commit

- `d95d3a0` feat(evidence): promotion skips structurally-impossible and negated edges
- 仅 add 两个文件:`backend/app/services/mirror_promotion_service.py`、`backend/tests/test_mirror_promotion_to_final.py`(工作树其他无关改动未触碰)

## Review 修复(fail-open 回退,已并入最终 commit)

Review 指出:共享判定函数中治理查询无条件执行,在未迁移 `paper_evidence_task_items` 表(运行时切换的旧库)上每次晋升(preview + run)都会抛 `ProgrammingError` 整体失败。修复:

- `get_governance_skip_outcome` 将 raw SQL 查询包入 `try/except SQLAlchemyError`(`from sqlalchemy.exc import SQLAlchemyError`),异常时 `_logger.warning` 记录后返回 `None`(fail-open,不阻断晋升)。
- 新增模块级 `import logging` + `_logger = logging.getLogger(__name__)`。
- 新增测试 `test_evidence_table_missing_fails_open`:governance 查询 mock 抛 `SQLAlchemyError` → `validate_promotion_eligibility` 仍返回 eligible(reason=None,不崩溃)。
- 回归:`test_mirror_promotion_to_final.py` 31 passed;`-k promotion` 82 passed。

## Concerns / 与 brief 的偏差

1. **preprocess_outcome 不在 mirror 对象上**:brief 提示「查询已含该列」,但实际该列在 `paper_evidence_task_items` raw 表,晋升服务通过 `(target_type, target_id)` JOIN 语义(独立 raw SQL 查询)取最新一条 outcome —— 这是唯一与 brief 的出入,已按真实代码实现(brief 亦允许「以实际代码为准」)。
2. **triple 无治理跳过**:`paper_evidence_task_items` 的 evidence 任务不支持 triple 目标(`TARGET_MODELS` 无 triple),故 triple 不参与治理跳过。
3. **永久性语义**:跳过通过每次晋升时重新判定实现(非一次性状态位);对象本身状态不改变、不写标记列,reason code 落在 promotion record 的 `message`(及 preview 的 `ineligible_reason`),即「标记跳过原因」。
4. **取值口径**:同一目标可能有多条历史 task item(重跑),取 `created_at` 最新一条为准。
