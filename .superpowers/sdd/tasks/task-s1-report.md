# Task S1 Report: 三栏骨架 + ContextBar + StepPills + 统一对象队列

## Status: DONE (committed)

## Commit

`feat(evidence-center): 三栏骨架 + ContextBar + StepPills + 统一对象队列`

## What Was Delivered

### 页面骨架 (EvidenceCenterPage.tsx)
- 页面改为 `evidence-center` (flex column) + `evidence-center-layout` 三栏 grid:
  `grid-template-columns: 230px minmax(620px, 1fr) 370px`
- 左栏 `<aside class="evidence-left">` → `<ObjectQueue>`;中栏 `evidence-main` → 模块内容(hint + 五模块条件渲染,模块内容本身未动);右栏 `<aside class="evidence-right">` → `<RightPanel module={state.module} />` 占位
- **papers 模块例外**:加 `evidence-center-layout-full` 修饰类 → 单列全宽,左右栏隐藏
- 页面级任务名推导:`useEffect` 按 `state.taskId` 从 `listPaperEvidenceTasks` 查 name(target_type 兜底),传给 ContextBar
- `currentIndex` 由 queue 匹配 `state.targetType/targetId` 推导,无匹配时取 0
- 刷新按钮 → `window.location.reload()`(S1 兜底实现);返回数据中心 → hash `#/data-center`

### ContextBar (components/ContextBar.tsx)
- props 按 brief:`{ targetLabel, targetType, granularity, confidence, evidenceCount, taskName, queueIndex, queueTotal, taskStatus, onBackToDataCenter, onRefresh }`
- 显示:对象名(空时「未选择对象」)/ 类型 / 粒度(仅提供时)/ 置信度百分比 / 证据数 / 任务名·进度 `(idx+1)/total`(空队列显示「等待处理对象」)/ 状态 chip / 刷新 + 返回数据中心按钮
- 纯展示组件,数据由页面从 Context queue + state 推导后传入

### StepPills (components/StepPills.tsx)
- 五步胶囊:确认对象 → 查找论文 → 找到原文 → 人工审核 → 确认晋升
- `MODULE_TO_STEP`: tasks=0, papers=0, candidates=1, review=3, promotion=4(严格按 brief);currentStep=0 时无高亮;仅当前步 `.active`

### ObjectQueue (components/ObjectQueue.tsx)
- props:`{ queue, currentIndex, onSelect, showStats? }`(showStats 默认 true,暂未使用)
- 标题「待处理对象」+ 计数;统计:待审核(pending/searching/extracting/awaiting_review)/ 已完成(completed/skipped)/ 失败(failed)
- 「只看未处理」checkbox(组件内本地 state 过滤)
- 紧凑对象卡:名称 / `target_type · 置信度` / 状态色(ok/warn/bad/info/muted)/ 证据数;当前对象浅背景 + 左侧 3px 强调条
- 空队列占位「队列为空」

### RightPanel (components/RightPanel.tsx)
- 右栏插槽占位,按 module 显示标题:tasks=任务与队列概览 / candidates=检索与候选 / review=审核决策 / promotion=晋升确认 / papers=论文详情(papers 下不渲染)
- S2-S5 各模块后续填充

### EvidenceCenterHeader.tsx
- 保留五模块导航(新增 `data-testid="evidence-module-nav"`);「返回数据中心」按钮移入 ContextBar(避免重复文本)

### types.ts
- 新增 `QUEUE_STATUS_LABEL`(QueueStatus → 中文)与 `queueStatusTone`(状态 → 色板),ObjectQueue/ContextBar 共用;各模块内部自己的状态映射未动

### styles.css
- `.evidence-center` 高度: `calc(100vh - var(--topbar-h) - var(--log-console-actual-height, var(--log-console-height-collapsed)) - 44px)`(适配 main padding 22px*2 + 底部日志栏)
- `.evidence-center-layout` 三栏 grid + `-full` 单列修饰;三栏独立 `overflow-y: auto`,白底轻 border + shadow
- `.evidence-context-bar`(对象信息行 + chips + actions)、`.evidence-step-pills`(胶囊 + 编号圆点 + active 主色)、`.evidence-queue-*`(统计/过滤/紧凑卡/状态色/左强调条)

## Tests (TDD RED → GREEN)

- 扩展 `EvidenceCenterPage.test.tsx`:
  - 三栏骨架渲染(left/main/right + queue/right-panel testid)
  - papers 模块全宽(隐藏左右栏)
  - 右栏占位标题随 module 切换
  - ContextBar 显示对象/类型/置信度/证据数/进度(1/2)
  - 空队列 ContextBar 占位
  - ObjectQueue 条目渲染 + 当前项高亮
  - StepPills 五步渲染 + 随 module 高亮(candidates→确认对象,review→找到原文)
  - 既有测试适配:导航断言改用 `within(nav)`,「人工审核」点击改用 `getAllByText[0]`(nav 与 step pill 文本重复)
- 新建 `ContextBar.test.tsx`(对象信息/进度/空态/按钮回调)、`StepPills.test.tsx`(五步/各 step 高亮/0 无高亮)、`ObjectQueue.test.tsx`(统计/点击回调/只看未处理过滤/空态)

## Verification

- `npx vitest run src/pages/evidence-center/` — 10 files, 71 tests passed
- `npx vitest run` (全量) — 13 files, 85 tests passed
- `npm run build` — 0 TS errors,build 成功(仅有既有的 chunk-size/dynamic-import 警告,与本次改动无关)

## Concerns / Notes for Follow-ups

1. **模块内左队列仍在**:EvidenceCandidatesModule 内部 240px 队列与 ObjectQueue 并存(骨架期有意为之);S2/S3 需删除模块内队列并复用 Context queue
2. **granularity 为 null**:ContextBar 的 granularity 需 `getEvidenceTarget` 数据,模块已各自拉取 DTO;S2+ 可考虑在 Context 层缓存 DTO 或由 ObjectQueue 条目携带
3. **onRefresh 现为整页 reload**,后续可改为仅重拉当前模块数据
4. **页面高度 calc 依赖 `--log-console-actual-height` 变量**;日志台展开时页面按实际高度适配(未见异常)
5. 右栏当前为占位,`RightPanel` 标题与 S2-S5 任务对齐(tasks 概览 / candidates 检索 / review 审核决策 / promotion 晋升确认)
