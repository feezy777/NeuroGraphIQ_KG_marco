# Task 6 Report: 已完成区 + 回退重新审查（含前端 API wrapper）

Status: **DONE_WITH_CONCERNS**（1 处 brief 测试 fixture 缺陷已修复，见「Deviation」节）

## 实现内容

1. **`frontend/src/api/endpoints.ts`**（追加，保留工作树已有未提交改动）
   - 在 `completePaperEvidenceTaskItem` 之后追加 `reopenPaperEvidenceTaskItem(taskId, itemId)` → `POST /api/ontology/evidence/batch/{taskId}/items/{itemId}/reopen`，返回 `Promise<{ task_id; item_id; status }>`。
   - 已核实该路径与 Task 1 后端端点一致（`backend/app/routers/ontology.py` `@router.post("/evidence/batch/{task_id}/items/{item_id}/reopen")`）。

2. **`frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`**
   - lucide import 改为 `ChevronDown, ChevronRight, Inbox`；endpoints import 加 `reopenPaperEvidenceTaskItem`。
   - 新增 state：`doneOpen` / `reopeningId` / `confirmId` / `actionError`。
   - `unfinished/filtered` memo 后追加 `doneItems`（completed 按 `updated_at` 倒序）与 `handleReopen`（两步确认：第一次点击进入确认态并 3s 自动解除，第二次调用 reopen + `loadItems()` 刷新；失败设置 `actionError`）。
   - JSX 在待处理区之后、根 div 之前插入已完成折叠区：toggle（`evidence-queue-done-toggle`）、条目（`evidence-queue-done-item-{target_id}`）、回退按钮（`evidence-queue-reopen-{target_id}`，含 回退重新审查/确认回退?/回退中… 三态）。
   - 与 brief Step 4 代码逐字一致。

3. **`frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx`**
   - 在 describe 块内追加 3 条用例（折叠区倒序、两步确认回退、回退失败错误提示）。
   - 断言行与 brief 完全一致；仅对新用例的 `makeItem` 调用补充了 `label` 覆盖（见 Deviation）。

4. **`frontend/src/styles.css`**（文件末尾追加，保留已有未提交改动）
   - 追加 `.evidence-queue-done*` 4 条样式，与 brief Step 5 一致。

## TDD 证据

### Step 2: RED（先追加 3 条测试再运行）

```
cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx
```

输出要点：3 条新用例全部失败，失败点均为找不到 `evidence-queue-done-toggle`（组件尚无已完成区）：

```
TestingLibraryElementError: Unable to find an element by: [data-testid="evidence-queue-done-toggle"]
 ❯ src/pages/evidence-center/components/TaskItemQueue.test.tsx:166:11
    166|     await waitFor(() => expect(screen.getByTestId('evidence-queue-done…
...
 Test Files  1 failed (1)
      Tests  3 failed | 5 passed (8)
```

（既有 5 条 Task 5 用例保持通过 → RED 是新增用例专属，无回归。）

### Step 6: GREEN（实现完成后）

```
cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx
```

```
 Test Files  1 passed (1)
      Tests  8 passed (8)
   Start at  15:10:32
   Duration  933ms ...
```

## 附加验证

- `npx tsc -b` → exit 0，0 TypeScript 错误。
- `npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx` → 9/9 通过（tasks 模块未回归）。
- `npx vitest run src/pages/evidence-center` → 4 个文件 16 条失败，**全部为与本次改动无关的基线失败**（详见下节），本任务涉及文件无失败。

## Deviation（重要）

**问题**：brief Step 1 的 3 条新用例用 `getByText('live')` / `getByText('done-new')` 作等待哨兵，但既有 `makeItem` 辅助函数默认 `label: 'Conn'`，而卡片渲染 `item.label || item.target_id` —— 文本 'live'/'done-new' 永远不会出现在 DOM 中，任何实现都无法让这两条用例通过。实测：按 brief 逐字实现后，用例 1、2 卡死在 `getByText('live')`，用例 3 卡死在 `evidence-queue-reopen-done-1`（该条实际已实现，但前两条失败阻塞了断言顺序）。

```
FAIL > 已完成折叠区...
TestingLibraryElementError: Unable to find an element with the text: live.
FAIL > 回退两步确认...
TestingLibraryElementError: Unable to find an element with the text: live.
```

**修复**：仅对新追加用例的 `makeItem` 调用补充 `label` 覆盖（`label: 'live'`、`label: 'done-new'`、`label: 'done-old'`、`label: 'done-1'`）。所有断言行与 brief 保持逐字一致，测试语义不变（label 是真实可见文本，属行为验证）。组件/endpoints/CSS 三处代码与 brief 逐字一致，未做任何改动。

来源判断：计划文档 `docs/superpowers/plans/2026-08-13-evidence-tasks-page-redesign.md` 中同一测试代码与既有 `makeItem`（`label: 'Conn'` 默认）并存，系计划书自身 fixture 疏漏，非 Task 5 实现偏差。

## 基线失败说明（非本任务引入）

evidence-center 全量运行时 16 条失败分属 4 个未触碰文件，与 reopen/已完成区无关：

- `EvidenceCenterPage.test.tsx`（3）：仍断言旧 `evidence-queue` testid 与「已从数据中心恢复…」旧 ObjectQueue 行为（Task 3-5 已重构）。
- `EvidencePromotionModule.test.tsx`（9）：断言「确认晋升」而实现已改「确认入库」等晋升模块行为偏差。
- `EvidenceCandidatesModule.test.tsx`（2）、`PaperCandidateCard.test.tsx`（1）：草稿 hash 下划线格式、DOI 行展示偏差。

均属计划 Task 7「全量验证 + 最终评审」范畴（Task 5 Step 7 亦注明「基线失败保持原状」）。

## 自查结论

- 约束遵守：未执行任何 git 命令；仅改动 brief 列出的 4 个文件；endpoints.ts / styles.css 均为追加式改动，未触碰既有未提交内容；新测试未断言 `module=tasks` URL 字符串。
- 回退成功路径：`handleReopen` 用 `item.id`（非 target_id）调用 reopen，与后端 endpoint 的 `item_id` 语义一致；测试断言 `toHaveBeenCalledWith('t1', 'b')` 已验证。
- 已知小事项（与 brief 代码一致，非缺陷）：`window.setTimeout` 3s 解除确认态未在卸载时清理（React 18 不再对卸载后 setState 告警，且用函数式 prev 守卫）；`handleReopen` 在无 taskId 时会以空串调用（实际不可达——无 taskId 时队列为空、无按钮可点）。
- 交互细节：确认态按钮仍可点击第三次（再次触发回退）——这正是两步确认语义（第二次点击即执行），符合 brief 设计。

## 文件清单

- `frontend/src/api/endpoints.ts` — 追加 `reopenPaperEvidenceTaskItem`
- `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx` — 已完成折叠区 + 两步确认回退
- `frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx` — 追加 3 用例（+label fixture 修复）
- `frontend/src/styles.css` — 末尾追加已完成区样式
