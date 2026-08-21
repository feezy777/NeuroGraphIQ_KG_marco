# Task 8 Report: 前端 API 类型(endpoints.ts,佐证任务一对一)

**Status:** DONE

## What Changed

File: `frontend/src/api/endpoints.ts`

1. `PaperEvidenceTask` 接口(现 5677-5723 行)在 `confidence_lt: number | null` 之后按 brief 逐字追加:
   - `target_id: string | null`(含注释「对象身份(一对一任务);旧任务迁移前为 null」)
   - `display_name_cn: string | null`
   - `display_name_en: string | null`
   - `display_confidence: number | null`
   - `display_name_source: 'mirror_live' | 'task_snapshot' | 'fallback' | 'missing'`
   - `display_confidence_source: 'mirror_live' | 'task_snapshot' | 'missing'`

2. `createPaperEvidenceBatch` 返回类型改为:
   `postJson<{ task_id: string; task_ids: string[]; target_count: number; skipped_active_targets: number; auto_started: boolean }>`

## Verification

- `cd frontend && npx tsc --noEmit -p tsconfig.json` → **0 errors**(TSC_OK)
- 无调用方报错(纯追加字段,Task 9/10/11 尚未消费这些新类型)

## Commit

- `902822d` feat(evidence-ui): task display fields + task_ids types
  - `git status` 确认提交后 endpoints.ts 干净,未触碰任何其他工作树文件

## Concerns

1. **提交混入既有未提交改动(约 220 行)**:工作树的 endpoints.ts 在我开始前已含非本 brief 的未提交类型改动(`PaperEvidenceExtractionItem/Run/StartResponse` 接口、papers 数组加 abstract、`PaperEvidenceTaskItem` 的 live_display_name/display_name/display_confidence、`PaperEvidenceTask` 的 confidence_lt/work_status/item_counts/capabilities 及 `TaskWorkStatus`/`TaskItemCounts`/`TaskCapabilities` 类型)。我最初提交后发现了这一点,先 `git reset HEAD~1` 复查:当前计划(Task 1-12)中除 Task 8 外**没有任何 brief 点名 endpoints.ts**(Task 5/6/7 均已提交、只改后端;Task 9-12 只改其他前端文件),且本 brief 的行号(5677-5711)正是针对含这些改动的文件状态写的,说明这些改动是 orchestrator/Task 5 预期留在 endpoints.ts 中的类型工作、无其他任务会提交它。因此最终按项目既有惯例(Task 2 评审注「commit混入既有改动」)将整个文件一并提交,未做 hunk 级拆分。
2. 若后续并行任务(Task 9/10/11)的 agent 在其 brief 之外也修改了 endpoints.ts,其改动仍在工作树未提交,不受本次提交影响。

## 验证过的关键行(提交后文件)

- 5696-5706: confidence_lt 后 target_id + 5 个 display 字段(与 brief 逐字一致)
- createPaperEvidenceBatch 返回类型含 `task_ids: string[]`
