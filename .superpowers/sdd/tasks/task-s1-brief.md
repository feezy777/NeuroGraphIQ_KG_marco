### Task S1: 三栏骨架 + ContextBar + Step Pills

**Files:**
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`(页面级三栏 grid + 右栏插槽)
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterHeader.tsx`(模块导航保留 + 顶部 ContextBar)
- Create: `frontend/src/pages/evidence-center/components/ContextBar.tsx`
- Create: `frontend/src/pages/evidence-center/components/StepPills.tsx`
- Create: `frontend/src/pages/evidence-center/components/ObjectQueue.tsx`(左栏对象队列,从各模块提取统一)
- Test: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`(扩展)+ `ContextBar.test.tsx`

**Interfaces:**
- `ContextBar` props: `{ targetLabel, targetType, granularity, confidence, evidenceCount, taskName, queueIndex, queueTotal, taskStatus, onBackToDataCenter, onRefresh }`(数据从 Context queue + state 推导)
- `StepPills` props: `{ currentStep: number }`(STEPS = 确认对象/查找论文/找到原文/人工审核/确认晋升;step 由 queue/draft 推导,候选=1,审核=3,晋升=4)
- `ObjectQueue` props: `{ queue, currentIndex, onSelect, stats, filter, onFilterChange }`(标题「待处理对象」+ 统计待审核/已完成/失败 + 只看未处理 + 紧凑卡 + 当前对象浅背景左边强调)

**行为:**
- EvidenceCenterPage 布局:`<div className="evidence-center-layout">` grid 三栏;左栏 `<ObjectQueue>`;中栏模块内容;右栏 `<RightPanel module={state.module} />`(S2-S5 各模块填充右栏内容)
- 论文库模块例外:模块内部渲染全宽(骨架对 papers 模块隐藏左右栏,或模块内部全宽 grid)
- ContextBar 数据:queue 当前项(label/target_type/confidence/evidenceCount)+ state.taskId → taskName(从 tasks 缓存或 listPaperEvidenceTasks 找)+ 进度(idx+1/total)

**测试:** 三栏渲染;右栏随 module 切换占位;ContextBar 显示对象/进度/返回数据中心;StepPills 五步渲染

**提交:** `feat(evidence-center): 三栏骨架 + ContextBar + StepPills + 统一对象队列`

---

