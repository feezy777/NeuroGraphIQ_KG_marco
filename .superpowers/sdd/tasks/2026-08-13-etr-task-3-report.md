# Task 3 报告: 任务列表视图(任务卡片网格 + 全宽布局 + 上下文导航语义)

状态: **DONE_WITH_CONCERNS**

## 已实现内容(严格按 brief 步骤执行)

| Step | 内容 | 结果 |
|------|------|------|
| 1 | 整体替换 `EvidenceTasksModule.test.tsx` 为列表视图用例(与 brief 逐字一致) | 完成 |
| 2 | RED 验证 | 5 failed(符合 brief Expected) |
| 3 | 整体替换 `EvidenceTasksModule.tsx`(列表视图 + 详情占位,与 brief 逐字一致) | 完成 |
| 4 | `EvidenceCenterContext.tsx` 外科式编辑:接口加 `closeTask`;`openTask` module 改 'tasks' + 注释更新;新增 `closeTask` 实现;value useMemo 与依赖数组加 `closeTask` | 完成 |
| 5 | `EvidenceCenterPage.tsx` 外科式编辑:`isTasksList`/`isFullWidth` 条件 + 三处 `isFullWidth` 替换(布局 className / 左栏 aside / 右栏 aside) | 完成 |
| 6 | `styles.css` 末尾追加任务卡片网格样式 | 完成 |
| 7 | `EvidenceCenterPage.test.tsx` 「papers 模块例外」测试之后追加 tasks 列表全宽用例 | 完成 |
| 8 | 运行两个测试文件 | 见下方 GREEN 证据(与 brief Expected「模块 5 passed」不符,2 个 brief 自带缺陷) |

## TDD 证据

### RED(Step 2)

```
cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx

Test Files  1 failed (1)
     Tests  5 failed (5)
```

失败原因与 brief Expected 一致:旧模块渲染「未选择佐证任务」空态,不存在 `evidence-task-card-grid` / 错误重试 / 卡片排序等新行为。

### GREEN(Step 8)

```
cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/EvidenceCenterPage.test.tsx

Test Files  2 failed (2)
     Tests  7 failed | 20 passed (27)
```

- 模块测试:`3 passed | 2 failed`(失败均为 brief 自带缺陷,详见 Concerns)
- 页面测试新增用例「tasks 列表视图全宽:无左右栏,渲染任务卡片区」:**通过**(单独运行 `-t "tasks 列表视图全宽"` → `1 passed | 21 skipped`)
- 页面测试基线失败(非本任务引入,保持原状):五模块接线 promotion / 其他模块左栏 ObjectQueue / initial-queue ObjectQueue candidates / 切换任务后 URL(Task 4 重写)
- 类型检查:`npx tsc --noEmit` → 0 errors

## 文件改动清单

1. `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\pages\evidence-center\modules\EvidenceTasksModule.tsx` — 整体替换(brief 内容)
2. `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\pages\evidence-center\modules\EvidenceTasksModule.test.tsx` — 整体替换(brief 内容)
3. `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\pages\evidence-center\EvidenceCenterContext.tsx` — 外科式:接口(行37)、`openTask` 重写 + `closeTask` 新增(行157-175)、value(行191)、依赖数组(行219);文件其余未提交改动全部保留
4. `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\pages\evidence-center\EvidenceCenterPage.tsx` — 外科式:行59-62 新条件 + 行92/93/115 三处 `isFullWidth`;文件其余未提交改动全部保留
5. `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\pages\evidence-center\EvidenceCenterPage.test.tsx` — 仅追加 1 个用例(在「papers 模块例外」之后)
6. `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\frontend\src\styles.css` — 仅文件末尾追加卡片网格样式(已确认 `--danger/--shadow/--radius` token 存在)

## 自审发现

- Context 编辑后 grep 验证:`closeTask` 出现在接口/实现/value/依赖数组四处,签名一致;`openTask` 现为 `apply({ taskId, targetType: null, targetId: null, module: 'tasks' })` + 进度重置。
- Page 编辑后 grep 验证:`isPapers` 仅剩定义处一行,三处使用点(布局 className、左栏、右栏)均为 `isFullWidth`;`isTasksList` 定义与 brief 逐字一致。
- 模块与测试文件内容与 brief 逐字一致(硬约束满足);未改动后端及任何其他前端文件;未执行任何 git 操作。
- `useGlobalGranularity` 有默认 context 值,无 Provider 包裹时测试安全;`CreateBatchTaskDialog open=false` 不触发副作用;tsc 0 errors。

## Concerns(需控制器裁决)

### C1: 模块测试「排序」失败 — brief 测试自带选择器缺陷
`cardOrder` 用 `[data-testid^="evidence-task-card-"]` 前缀匹配,会同时命中网格容器的 `data-testid="evidence-task-card-grid"`:

```
AssertionError: expected [ 'evidence-task-card-grid', …(4) ] to deeply equal [ …(4) ]
```

实际实现排序正确(进行中→待审核→其他,组内时间倒序),是断言集合多收了 grid 元素。约束要求测试文件与 brief 完全一致,故未擅自修改。建议修复(择一):cardOrder 过滤掉 `evidence-task-card-grid` 一项,或选择器改为 `:not([data-testid="evidence-task-card-grid"])`。

### C2: 模块测试「点击任务卡片」失败 — URL 不写 module=tasks
`evidenceCenterUrl.ts` 的 `buildEvidenceUrl` 第 30 行 `if (s.module !== 'tasks') params.set('module', s.module)` 省略 tasks 模块参数,因此点击卡片后 hash 为 `#/evidence-center?task_id=t1`:

```
AssertionError: expected '#/evidence-center?task_id=t1' to contain 'module=tasks'
```

该文件不在本任务允许的 6 文件清单内,故未改动。注意:计划中 Task 4(详情自动选中后断言 `module=tasks`)与 Task 5(队列点击 `openTarget(...,'tasks')` 后断言 `module=tasks`)存在完全相同的期望,均会撞上此行为。建议修复:把该行改为无条件 `params.set('module', s.module)`(一行改动,需控制器授权该文件),或同步调整各任务测试断言。

### C3: 页面测试「右栏随 module 切换」由通过变失败(设计使然的中间态)
该用例以 `module=tasks`(无 task_id)渲染并断言右栏标题含「任务」;本任务按 brief Step 5 将 tasks 列表视图设为全宽、隐藏右栏(新增用例断言 `.evidence-right` 为 null),两者直接矛盾:

```
AssertionError: expected '' to contain '任务'
```

计划本身已安排 Task 5 Step 5 重写该用例(改用 `task_id=ta` 断言待处理队列),即此失败为 Task 3→5 之间的预期中间态。按 brief 授权范围(仅追加新用例)未提前改写,已留待 Task 5。

### C4: 页面基线失败保持原状(非本任务引入)
`五模块接线 promotion` / `其他模块左栏 ObjectQueue` / `initial-queue ObjectQueue candidates` / `切换任务后 URL`(Task 4 计划重写)——与任务开始前基线一致,前后对比:基线 4 failed | 17 passed (21) → 现 5 failed | 17 passed (22)(+C3 一项,+1 个本任务新增并通过的用例)。

## 建议

控制器可:(a) 接受 C1/C2 为计划缺陷并在后续任务统一修正(建议同时修 `evidenceCenterUrl.ts` 一行,一次性解除 Task 3/4/5 的 URL 断言阻塞);(b) 授权我在此工作树内做最小修复(buildEvidenceUrl 一行 + cardOrder 过滤一行,不违反其余约束)。
