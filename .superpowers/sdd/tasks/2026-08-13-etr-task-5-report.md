# Task 5 报告:右栏待处理队列(TaskItemQueue + RightPanel 接入)

**状态:** DONE(含 1 处对 brief 的必要偏差,详见「Deviation」)

## 实现内容

按 brief `2026-08-13-etr-task-5-brief.md` 的 Steps 1-7 顺序执行:

1. **新建 `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`** — 右栏待处理队列组件:
   - 读 `state.taskId`,通过 `listPaperEvidenceTaskItems(taskId, { limit: 200 })` 拉取条目
   - `sortByConfidenceAsc(items.filter(isUnfinishedItem))` 置信度升序(null 最前),completed/failed 不进队列
   - 回路/连接/功能筛选 chips(基于 Task 2 的 `TARGET_TYPE_GROUPS`/`groupOf`),含计数
   - 队列条目卡片 `evidence-queue-item-{target_id}`:label/类型/置信度大字/状态 chip/AI 方向;当前对象(`state.targetType + state.targetId`)高亮
   - 点击条目 → `openTarget(type, id, 'tasks')` 保持 tasks 模块
   - 空态「全部处理完成」(`evidence-queue-empty`)、错误 + 重试、≥200 条截断提示
2. **新建 `frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx`** — 5 条测试,代码与 brief Step 1 完全一致
3. **修改 `frontend/src/pages/evidence-center/components/RightPanel.tsx`** — 外科式替换 tasks 分支:
   - 删除 `import { TaskSummary }`,新增 `import { TaskItemQueue }`
   - 解构中删除 `taskSummary, taskSummaryActions, openTask,`
   - tasks 分支替换为 `<TaskItemQueue />`(保留 `aside.evidence-right-panel` 外壳)
   - candidates/review/promotion 分支与工作树中未提交的候选模块改动(PassageSummary 等)完整保留
4. **修改 `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`** — 「右栏随 module 切换:占位标题(任务/审核)与队列(candidates)」整条替换为「右栏随 module 切换:tasks 详情渲染待处理队列,candidates 渲染待处理对象队列」(brief Step 5 原样)
5. **修改 `frontend/src/styles.css`** — 文件末尾追加队列样式块(brief Step 6 原样,append-only,未触碰任何既有内容)

## TDD 证据

### RED(Step 2)

首次以 `.ts` 运行因 brief 文件名与 JSX 内容矛盾被 esbuild 拦截:

```
FAIL  src/pages/evidence-center/components/TaskItemQueue.test.ts
Error: Transform failed with 1 error:
.../TaskItemQueue.test.ts:48:72: ERROR: Expected ">" but found "/"
Plugin: vite:esbuild
```

改名为 `.tsx` 后重跑,得到 brief 预期的失败:

```
FAIL  src/pages/evidence-center/components/TaskItemQueue.test.tsx
Error: Failed to resolve import "./TaskItemQueue" from
"src/pages/evidence-center/components/TaskItemQueue.test.tsx". Does the file exist?
Test Files  1 failed (1)
Tests  no tests
```

### GREEN(Step 7 前,组件测试)

```
npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx
Test Files  1 passed (1)
Tests  5 passed (5)
```

### Step 7 三文件验证

```
npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx \
  src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx \
  src/pages/evidence-center/EvidenceCenterPage.test.tsx
Test Files  1 failed | 2 passed (3)
Tests  3 failed | 34 passed (37)
```

- TaskItemQueue:5 passed ✓
- EvidenceTasksModule:9 passed ✓(34 − 20 页面通过 − 5 队列 = 9)
- 页面测试 23 条:20 通过,3 失败且**恰为基线 3 条**:
  - `五模块接线:module='promotion' 渲染对应模块`(promotion wiring)
  - `其他模块左栏仍渲染 ObjectQueue(review/promotion/tasks 布局不变)`(ObjectQueue-left)
  - `无任务时 initial-queue 恢复的条目渲染在页面级右栏 ObjectQueue(candidates)`(initial-queue)
- 重写后的「右栏随 module 切换」单独运行:`1 passed | 22 skipped` ✓
- `npx tsc -b`(build 类型检查,不含测试文件)exit 0 ✓

## Deviation(需控制器知悉)

**测试文件名 `.ts` → `.tsx`**:brief Files 清单写 `TaskItemQueue.test.ts`,但 Step 1 给出的代码含 JSX,esbuild 拒绝在 `.ts` 中解析 JSX(`Expected ">" but found "/"`)。无法同时满足「文件名」与「exact code」。取最小偏差:文件名改为 `.tsx`(项目惯例:evidence-center 全部组件测试均为 `.test.tsx`;react 规则亦要求 JSX 文件用 .tsx)。测试代码本身与 brief 逐字一致,未改。

## 自审发现与关注点

1. **`reopenPaperEvidenceTaskItem` 尚不存在于 `frontend/src/api/endpoints.ts`**(grep 全仓仅 EvidenceTasksModule.test.tsx 的 mock 工厂有该键)。新测试按 brief 在 mock 工厂里声明了它,`beforeEach` 也 mock 了它;但 `TaskItemQueue` 组件并不 import 它,故无运行时调用。`tsconfig.app.json` exclude 测试文件,`npm run build` 不受影响。Task 6 接入回退重审时需真正在 endpoints.ts 添加该函数。页面测试的 vi.mock 工厂未补该键,按 brief 说明未预先添加,运行未报错。
2. **RightPanel.tsx 中 `import { ObjectQueue }` 未使用**——此为我改动前工作树中已存在的状态(候选模块未提交改动遗留),不属于本任务范围,按指令保留未动。
3. **Context 仍保留 taskSummary/taskSummaryActions**——brief 只要求从 RightPanel 解构中删除;`EvidenceCenterContext.tsx` 不在允许改动的 5 个文件内,TaskSummary 组件亦未被删除(Task 6/7 如需要可另行清理)。
4. **全 evidence-center 套件基线**:27 个文件 239 条,16 失败(3 页面基线 + 10 EvidencePromotionModule + 2 EvidenceCandidatesModule + 1 PaperCandidateCard)。后 13 条已核实与本任务无关:promotion 失败均为 `module="promotion"` 下 `promotion-pending-row`/晋升 UI 内部断言,属工作树未提交的晋升模块改动所致;候选/卡片失败同理。本任务未改这些文件,亦不可能通过 RightPanel tasks 分支或 CSS append 影响它们。
5. 断言未包含 `module=tasks` URL 字符串(buildEvidenceUrl 省略默认 module),符合硬约束。
6. 未执行任何 git 命令。

## 改动文件(绝对路径)

- `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\pages\evidence-center\components\TaskItemQueue.tsx`(新建)
- `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\pages\evidence-center\components\TaskItemQueue.test.tsx`(新建,brief 中名为 .ts)
- `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\pages\evidence-center\components\RightPanel.tsx`(tasks 分支替换 + import/解构清理)
- `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\pages\evidence-center\EvidenceCenterPage.test.tsx`(1 条测试替换)
- `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\styles.css`(末尾追加)
