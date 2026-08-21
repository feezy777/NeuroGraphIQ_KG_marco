# V2-T3 报告:页面三栏常显 + 左栏 Claim + 删除 TaskListPanel

**日期:** 2026-08-14
**结论:** DONE。TDD 全流程(RED→GREEN)完成;brief 指定的三文件测试结果与预期完全一致;tsc exit 0;嵌入模式未提交改动全部保留。

---

## 1. 实现内容

### 1.1 `EvidenceCenterPage.test.tsx`(Step 1)
- 删除「tasks 列表视图全宽:无左右栏,渲染任务卡片区」整条测试。
- 删除「详情视图左栏返回按钮回到任务列表」整条测试(返回按钮已移入中栏,由模块测试覆盖)。
- 替换「右栏随 module 切换:…」为 brief 给定版本(去掉 `task_id=ta`,直接 `module=tasks`)。
- 新增「tasks 三栏常显:左栏 Claim 面板,中栏任务区,右栏队列」测试(brief 给定代码逐字使用)。
- 无任何 `module=tasks` URL 字符串断言。

### 1.2 `EvidenceCenterPage.tsx`(Step 3,外科式)
- 删除 `import { TaskListPanel } from './components/TaskListPanel'`。
- `isPapers / isTasksList / isFullWidth` 三行改回单一 `const isPapers = state.module === 'papers'`。
- 其余三处 `isFullWidth` 全部改回 `isPapers`:布局 className(88 行)、左栏 aside 条件(89 行)、右栏 aside 条件(107 行)。
- 左栏分支原来的三元(`tasks ? <TaskListPanel/> : <ClaimSummaryPanel/>`)替换为无条件 `ClaimSummaryPanel`(brief 给定代码)。
- 嵌入模式改动全部保留并逐行核对:`embedded` prop、`EvidenceModuleNavButton` 导航、`ContextBar/StepPills` 的 `!embedded` 条件、`onBackToDataCenter`/`onRefresh` 回调,均未被触及。

### 1.3 `TaskListPanel.tsx`(Step 3.4)
- 已从文件系统删除(用 Bash `rm`,非 git 命令)。git index 中的删除由控制器外科式处理。
- 删除前 grep 确认全库仅 `EvidenceCenterPage.tsx` 引用它;删除后再次 grep,frontend/src 中零残留(`TaskListPanel|isTasksList|isFullWidth` 均无匹配)。

---

## 2. TDD 证据

### 2.1 Step 2 — RED(测试先行,先改测试再跑)

命令:`cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx`

结果:5 failed | 17 passed (22),失败项:

```
× 五模块接线:module='promotion' 渲染对应模块 1015ms        ← 预存基线
× 其他模块左栏仍渲染 ObjectQueue(review/promotion/tasks 布局不变)  ← 预存基线
× 右栏随 module 切换:tasks 渲染待处理队列,candidates 渲染待处理对象队列  ← 本任务(旧全宽逻辑)
× tasks 三栏常显:左栏 Claim 面板,中栏任务区,右栏队列 21ms        ← 本任务(新增,预期失败)
× 无任务时 initial-queue 恢复的条目渲染在页面级右栏 ObjectQueue(candidates)  ← 预存基线
```

关键失败输出(与 brief 预期一致):

```
FAIL ... > tasks 三栏常显:左栏 Claim 面板,中栏任务区,右栏队列
AssertionError: expected null to be truthy
❯ EvidenceCenterPage.test.tsx:207:55
    207|     expect(container.querySelector('.evidence-left')).toBeTruthy()
    208|  (Received: null — tasks 列表视图仍是全宽,无左栏)

FAIL ... > 右栏随 module 切换:tasks 渲染待处理队列,candidates 渲染待处理对象队列
TestingLibraryElementError: Unable to find an element by: [data-testid="evidence-task-queue"]
(tasks 列表视图无右栏)
```

### 2.2 Step 4 — GREEN(页面修改 + 删文件后)

命令:`cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/components/TaskItemQueue.test.tsx`

结果:**Test Files 1 failed | 2 passed (3);Tests 3 failed | 38 passed (41)**

- EvidenceTasksModule.test.tsx ✅ 全绿;TaskItemQueue.test.tsx ✅ 全绿。
- 页面测试只剩 brief 预期的 3 个基线失败:

```
× 五模块接线:module='promotion' 渲染对应模块
× 其他模块左栏仍渲染 ObjectQueue(review/promotion/tasks 布局不变)
× 无任务时 initial-queue 恢复的条目渲染在页面级右栏 ObjectQueue(candidates)
```

- 本任务两条目标测试转绿:「右栏随 module 切换(tasks 无 task_id)」与「tasks 三栏常显」均 PASS。

### 2.3 附加验证

| 检查 | 结果 |
|------|------|
| `npx tsc --noEmit --pretty false` | ✅ exit 0 |
| grep `TaskListPanel\|isTasksList\|isFullWidth` in frontend/src | ✅ 零匹配 |
| 其他测试文件对已删行为的引用(`evidence-task-list-back` / `evidence-center-layout-full` / `evidence-task-card-grid`) | ✅ 无测试依赖已删按钮;layout-full 断言仅剩 papers 测试与新增 tasks 测试 |

---

## 3. Files Changed

| 文件 | 操作 |
|------|------|
| `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx` | 修改(3 处外科式编辑,嵌入模式保留) |
| `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx` | 修改(删 2 条、替换 1 条、新增 1 条) |
| `frontend/src/pages/evidence-center/components/TaskListPanel.tsx` | 文件系统删除(git rm 由控制器处理) |

未触碰后端、候选/审核/晋升模块、ValidationWorkbench、styles.css,也未执行任何 git 命令(仅一次只读 `git status --short` 确认 TaskListPanel.tsx 无未提交改动)。

---

## 4. Self-Review Findings

- ✅ 三处 `isFullWidth` → `isPapers` 全部替换,无遗漏(grep 验证)。
- ✅ 左栏、右栏条件均为 `!isPapers`,papers 全宽行为不变(papers 测试 PASS)。
- ✅ 嵌入模式(embedded prop、EvidenceModuleNavButton、ContextBar/StepPills 条件)逐行核对保留。
- ✅ 测试断言未检查 `module=tasks` URL 字符串。
- ✅ TaskListPanel.tsx 是唯一被删文件,且全库无残留引用。

## 5. Concerns(移交 V2-T4)

1. **证据中心全量套件预存失败 13 个(与本任务无关,建议 V2-T4 全量验证时排查):**
   额外跑了 `npx vitest run src/pages/evidence-center`(超出 brief 范围,仅作旁证):
   - `EvidencePromotionModule.test.tsx` 10 条失败(如「禁止项:无搜索控件 / 无 Europe PMC」:模块内找不到「待晋升」文本,约 1s/条);
   - `EvidenceCandidatesModule.test.tsx` 2 条(多论文草稿相关);
   - `PaperCandidateCard.test.tsx` 1 条(四行层级)。
   已核实这些测试**不渲染 EvidenceCenterPage**(promotion 测试自组"模块+右栏"布局;其余为纯模块/卡片测试),且我未触碰相关文件,故为分支上预存失败,非本任务引入。
2. 页面测试 3 个基线失败(promotion 接线 / 其他模块左栏 ObjectQueue / initial-queue)按 brief 属预期,留待 V2-T4 处理。
3. TaskListPanel.tsx 的 git 删除由控制器执行;若控制器用 `git rm`,文件系统已删除不影响其工作(git rm 可直接暂存删除)。
