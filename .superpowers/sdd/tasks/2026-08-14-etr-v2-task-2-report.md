# V2 Task 2 Report: TaskItemQueue 全局模式 + 任务过滤

**日期**: 2026-08-14
**状态**: DONE_WITH_CONCERNS(仅 1 个低风险观察 + 仓库既有失败测试,见下文)
**Brief**: `.superpowers/sdd/tasks/2026-08-14-etr-v2-task-2-brief.md`

## 实现内容

TaskItemQueue 右栏队列新增「全局模式」:

1. **无 taskId(全局模式)**:并行拉取所有进行中(pending/running/paused)任务的 items(`Promise.allSettled`,单任务失败静默跳过),合并后走原有置信度升序排序;每条目附任务名徽章(`.evidence-queue-task-badge`,`data-testid="evidence-queue-task-badge-{taskId}"`),任务名来自 `taskNames` state(id → `t.name || t.target_type`)。
2. **有 taskId(任务模式)**:行为完全不变(保留 `latestTaskIdRef` 陈旧响应守卫),不显示任务徽章。
3. **回退兜底**:`handleReopen` 优先用条目携带的 `__taskId`(全局模式回退需要真实 taskId),任务模式回退到 `taskId`。
4. **样式**:styles.css 末尾追加徽章样式(仅追加,未触碰未提交改动)。
5. **测试**:vi.mock 工厂加 `listPaperEvidenceTasks`;describe 内追加 `makeTask` 辅助 + 3 个用例(全局合并排序+徽章 / 单任务失败不影响其他 / 任务模式无徽章)。原 8 用例未改动。

## TDD 证据

### Step 2 — RED

```
> cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx

 Test Files  1 failed (1)
      Tests  3 failed | 8 passed (11)
```

- × 全局模式:未选任务时并行拉取进行中任务 items,合并置信度升序,条目带任务徽章 (waitFor BNull 超时)
- × 全局模式:单任务 items 失败不影响其他任务 (waitFor B1 超时)
- × 任务模式:选中任务后只拉该任务 items(不显示任务徽章) (waitFor C1 超时,队列渲染错误态)

> 与 brief 预期「新增 2 条失败;第 3 条任务模式应通过」略有出入:RED 状态下第 3 条也失败。原因:全局模式未实现时测试 2 的两条 once-mock(`mockRejectedValueOnce`/`mockResolvedValueOnce`)从未被消费,泄漏到测试 3 的首次调用(该 mock 对 `listPaperEvidenceTaskItems` 的首次调用先 reject)。实现后测试 2 在自身内部消费掉两条 once-mock,测试 3 即恢复通过——GREEN 阶段验证无误。这是 RED 阶段的良性伪影,非测试缺陷。

### Step 4 / Step 6 — GREEN

```
> cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx

 Test Files  1 passed (1)
      Tests  11 passed (11)
```

与 brief 预期「11 passed」一致。

## 文件改动(仅 3 个,brief 允许范围)

| 文件 | 改动 |
|------|------|
| `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx` | imports + `listPaperEvidenceTasks`;`taskNames` state;`loadItems` 拆两模式;`QueueItemCard` 加 `taskName` prop + 徽章;待处理区渲染调用处传 `taskName`;`handleReopen` 的 `__taskId ?? taskId ?? ''` 兜底 |
| `frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx` | vi.mock 工厂加 `listPaperEvidenceTasks: vi.fn()`;describe 末尾追加 `makeTask` + 3 用例(逐字采用 brief 代码) |
| `frontend/src/styles.css` | 末尾追加 `.evidence-queue-task-badge` 样式(brief 逐字代码;12874 → 12880 行,纯追加) |

## 硬约束合规

- 未执行任何 git 命令。✓
- 仅改动上述 3 个文件,未动后端/候选/审核/晋升/EvidenceTasksModule/EvidenceCenterPage/RightPanel。✓
- 新测试未对 `module=tasks` URL 字符串做断言(仅作为输入 hash 设置,与 brief 逐字一致;断言均为 testid/文本/端点调用)。✓
- styles.css 仅追加。✓

## 验证

- `npx tsc -b`:TSC_EXIT=0,类型检查通过。
- 目标测试文件:11/11 通过(Step 4 与 Step 6 各跑一次均通过)。
- 全量 evidence-center 套件:227 passed / 16 failed / 1 skipped,失败集中在 4 个文件,与本次改动无关(见下)。

## 自审发现与关注点

1. **[预存在,非本次引入] evidence-center 套件 16 条失败**:
   - `EvidencePromotionModule.test.tsx` 10 条、`EvidenceCandidatesModule.test.tsx` 2 条、`PaperCandidateCard.test.tsx` 1 条、`EvidenceCenterPage.test.tsx` 3 条。
   - 排除证据:(a) 前三者独立运行同样失败,且从不 import TaskItemQueue;(b) 对照实验:临时还原 TaskItemQueue.tsx 至改动前版本(未用 git),`EvidenceCenterPage.test.tsx` 仍 3 failed | 20 passed,与改动后一致;(c) RightPanel 仅在 `module==='tasks'` 时渲染 TaskItemQueue,而失败的 3 条 EvidenceCenterPage 用例均为 promotion/review/candidates 模块。结论:工作区中其他未提交改动导致,与本次任务无关,留给控制器/V2-T4 处理。
2. **[低风险观察] 全局模式无陈旧响应守卫**:全局拉取进行中,用户切到某个任务再切回全局时,乱序返回的全局响应可能与任务模式响应交错覆盖 `items`(brief 逐字代码即如此,未自行加守卫,遵循 brief)。实际影响小:`setItems` 前两模式都先清空再写入,最后一次完成的请求胜出;且全局模式下所有进行中任务最终都会重新拉取。
3. **[低风险观察] `listPaperEvidenceTasks()` 无分页参数**:与同目录 `TaskListPanel`、`EvidenceTasksModule` 现有用法一致(无参数调用),后端默认返回即可,未做改动。
4. **[低风险观察] `items.length >= 100` 截断提示在全局模式下统计的是合并后总数**,提示文案「仅显示前 100 条(按优先级截断)」在全局模式下语义变为「所有任务合并后前 100 条」。这是既有渲染逻辑的自然延续,brief 未要求改动。
5. 无 console.log、无硬编码密钥、无新依赖。

## 结论

Brief 的 6 个步骤全部执行完毕,目标测试 11/11 绿,tsc 通过,只动了 3 个允许文件,未执行 git 操作。全局模式行为与任务模式隔离干净,任务模式 8 条既有用例零改动全绿。
