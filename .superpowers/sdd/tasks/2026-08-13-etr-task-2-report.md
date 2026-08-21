# Task 2 Report: 前端纯工具（队列排序/分组 + 任务列表排序）

**Status: DONE_WITH_CONCERNS**（见 Concerns；任务本身全部完成并验证）

## Commit

- `12412d8` feat(evidence-center): 队列排序/类型分组与任务列表排序纯工具 + 单测
- 仅含 3 个文件、110 insertions（`git show --stat HEAD` 验证）。

## 实现内容（与 brief 逐字一致）

1. **Create** `frontend/src/pages/evidence-center/components/taskItemQueueUtils.ts`
   - `UNFINISHED_ITEM_STATUSES: string[]` — 7 个未完成状态
   - `isUnfinishedItem(item)` — 状态集合判定
   - `sortByConfidenceAsc(items)` — 拷贝后排序（不 mutate 入参）；null 置信度最前 → 升序 → 同值按 `label`（`|| target_id` 兜底）`localeCompare` 稳定排序
   - `TargetTypeGroup` type + `TARGET_TYPE_GROUPS`（回路/连接/功能，PRD R4 映射）+ `groupOf(targetType)`
2. **Modify** `frontend/src/pages/evidence-center/components/taskStatus.ts`（文件末尾追加，未动既有内容）
   - `IN_PROGRESS_TASK_STATUSES = ['pending','running','paused']`
   - `taskSortRank(t)` — 0=进行中 / 1=有等待审核 / 2=其他
3. **Test** `frontend/src/pages/evidence-center/components/taskItemQueueUtils.test.ts` — 5 用例，与 brief 完全一致

导出名/签名与 brief Interfaces 一节完全一致（Task 3/4/5 依赖）。`PaperEvidenceTaskItem` 已确认在 `frontend/src/api/endpoints.ts:5595` 存在且 25 个字段与测试 `makeItem` 逐一匹配。

## TDD 证据

**RED** — `cd frontend && npx vitest run src/pages/evidence-center/components/taskItemQueueUtils.test.ts`
```
 FAIL  src/pages/evidence-center/components/taskItemQueueUtils.test.ts
Error: Failed to resolve import "./taskItemQueueUtils" from ".../taskItemQueueUtils.test.ts". Does the file exist?
 Test Files  1 failed (1)
      Tests  no tests
```
（与 brief 预期的 Cannot find module 一致）

**GREEN** — 同命令实现后
```
 Test Files  1 passed (1)
      Tests  5 passed (5)
```

**类型检查** — `npx tsc --noEmit` exit 0（全项目 0 错误）。

## 自审发现与处理

1. **首次提交误吞 3 个已暂存 backend 文件（重要）**：首次 `git commit`（244d0ac）实际提交了 6 个文件——索引里在我 `git add` 之前已有 Task 1 遗留的已暂存文件（`backend/app/routers/ontology.py`、`backend/app/services/paper_evidence_service.py`、`backend/tests/test_paper_evidence_batch_phase4.py`），被一并提交。
   - **修复**：`git reset --soft HEAD~1` 后改用 `git commit -- <3个精确路径>` 重建提交为 12412d8，仅含 3 个目标文件。
   - **已验证**：backend 3 文件恢复为暂存态（`git status --porcelain` 显示 `M ` staged），且 `git diff --stat` 为空 → 工作树/索引内容零丢失。244d0ac 从未 push，已安全丢弃。
2. 提交时 LF→CRLF 警告为仓库既有 core.autocrlf 行为，无影响。
3. 未运行 `git add -A` / `git add .`；只 `git add` 了 brief Step 5 的 3 个精确路径。
4. `sortByConfidenceAsc` 使用 `[...items].sort(...)`，不修改入参；`label || target_id` 恒为 string（target_id 必填），localeCompare 安全。

## Concerns

- **遗留暂存 backend 文件**：3 个 backend 文件的暂存改动不是我做的，也不在我的提交中，现保持"已暂存"原样留待 Task 1/编排者处理。后续任何提交（尤其若再出现与索引整体提交相关的操作）需注意不要把这 3 个文件卷进其他任务提交；本任务已示范用 `git commit -- <paths>` 精确路径规避。
- `taskSortRank` 同组内"按创建时间倒序"由调用方（Task 3）在排序比较器中配合使用，本纯函数只负责返回秩值，符合 brief 签名。
