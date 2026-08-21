# V2 Task 1 Report: EvidenceTasksModule 重写为中栏三态

来源:`docs/superpowers/plans/2026-08-14-evidence-tasks-page-v2.md` Task 1
Brief:`2026-08-14-etr-v2-task-1-brief.md`

## Status: ✅ DONE

按 brief 步骤 1-6 顺序执行,全部 Expected 输出逐条吻合。

## 变更文件(仅 brief 所列 3 个)

| 文件 | 操作 |
|------|------|
| `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx` | 整体替换(brief Step 3 代码逐字采用) |
| `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx` | 整体替换(顶部 imports/20 endpoint vi.mock/makeTask/makeItem/cardOrder 保留;describe 替换为 8 条) |
| `frontend/src/styles.css` | 仅末尾追加 `.evidence-task-middle-bar` + `.evidence-task-card-selected`(原文件 12865 行未提交改动全保留,追加前确认两选择器原本不存在) |

未动后端、EvidenceCandidatesModule、EvidenceCenterPage、RightPanel、TaskItemQueue 等任何其他文件。未执行任何 git 命令。

## TDD 证据

### Step 2 RED

命令:`cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`

输出:`Test Files 1 failed (1)` / `Tests 2 failed | 6 passed (8)`

失败用例(与 brief 预期一致 —— 旧模块仍是两页结构):

```
× 全部完成任务:不自动选中,态② 对象卡片;点对象卡片 → 态③ 工作区  (evidence-task-object-c-done 不存在)
× 「← 任务列表」→ 回态①(URL 无 task_id)                          (evidence-task-middle-back 不存在)
❯ src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx:132:11 / :172:11
```

### Step 4 GREEN(模块重写后)

命令:同上

输出:`Test Files 1 passed (1)` / `Tests 8 passed (8)`(Duration 1.04s)

### Step 5 CSS 追加 + Step 6 复跑

追加后复跑:同样 `Tests 8 passed (8)`。

## 实现要点(brief 代码本身)

- **态①**(无 taskId):任务卡片网格 + `taskSortRank` 排序,`TaskCard` 支持 `selected`(样式 `evidence-task-card-selected`);工具栏提示文案改为「右栏为全局置信度优先级队列」。
- **态②/③**(有 taskId):中栏返回条 `evidence-task-middle-bar`(`data-testid="evidence-task-middle-back"` 调 `closeTask` 回态①);对象卡片 `ObjectCard`(`data-testid="evidence-task-object-{target_id}"`,复用 `evidence-conn-card` 系列样式 + 新增选中态);`sortObjects` = 未完成按置信度升序在前、已完成/其他在后;`targetResolved` 时嵌 `EvidenceCandidatesModule`(未改动该模块);空态 `testId="evidence-tasks-all-done"`;items 错误文案改为「对象列表加载失败」(替代旧「连接列表加载失败」)。
- 自动选中纠错 effect 保留旧模块语义(deps 不含 target,防旧快照抢回),仅注释更新。

## 回归与因果性核查(重要)

全量 `npx vitest run src/pages/evidence-center`:27 文件中 4 个文件失败(EvidenceCenterPage 3、PaperCandidateCard 1、EvidenceCandidatesModule 2、EvidencePromotionModule 10,共 16 失败)。

**已证明为既有失败、与本任务无关**,三重证据:

1. 静态分析:`EvidenceCenterPage.tsx:109` 仅在 `state.module === 'tasks'` 时挂载 `EvidenceTasksModule`;3 个失败页用例分别使用 module=promotion/review/candidates,本模块根本不渲染。其余 3 个失败文件(候选卡/候选模块/晋升模块)全库无任何对 `EvidenceTasksModule` 的引用(grep 确认仅 EvidenceCenterPage.tsx、taskStatus.ts、本模块及其测试引用)。
2. 因果互换实验(本任务允许的 3 文件范围内,临时恢复旧模块 → 跑 4 个失败文件 → 恢复新模块):旧模块下同样 4 文件失败(17 failed | 58 passed),失败集合一致 —— 证明与本次重写无关,是工作树中既有未提交改动(T2/T3 在途工作)造成的。
3. 页面级 tasks 用例在新模块下通过:「tasks 列表视图全宽:渲染任务卡片区」「右栏随 module 切换:tasks 详情渲染待处理队列」均在回归中绿。

新模块恢复后复跑本任务测试 8/8 通过;全项目 `npx tsc --noEmit` 零错误。

## 自审发现

- `sortObjects` 的 `rest` 未按状态/置信度排序(原样保留原始顺序),与 brief 注释「已完成/其他按状态排后」略有出入 —— 但代码为 brief 逐字要求,测试亦未断言 rest 顺序,故未改动。
- `evidence-task-detail-bar` 的旧样式(styles.css:12808-12813)残留未删除:brief 仅要求追加,旧样式为死样式,对渲染无影响,留给后续清理。
- `ObjectCard` 使用 `<div onClick>` 而非 `<button>`,无键盘可达性 —— brief 原文如此,未改动。
- `setItemsLoading(false)` 的 `finally` 分支在 taskId 已切换时不重置 loading:若切换任务时旧请求未返回,新 loadItems 会先 `setItemsLoading(true)` 再最终置 false,覆盖此窗口;依赖 `latestTaskIdRef` 的丢弃逻辑自洽(brief 原文,旧模块同构)。

## 遗留关注(供控制器/后续任务)

- 右栏队列仍为旧任务级实现,V2-T2「队列全局模式」与 V2-T3「页面三栏常显」接入前,上述 4 个既有失败文件预期不会转绿 —— 与本任务无关,勿回滚本任务成果。
- 中栏对象列表条数为空时提示「右栏已完成区回退对象」,该入口在 T5/T6 接入后才可用(与旧模块空态文案一致)。
