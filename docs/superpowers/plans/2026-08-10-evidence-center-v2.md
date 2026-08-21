# 证据中心 V2 视觉与交互重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development(推荐)或 executing-plans 逐任务执行。步骤用 `- [ ]` 跟踪。

**Goal:** 在已完成的五模块功能架构上,落地统一三栏骨架(230px + 主区 + 370px)、顶部 ContextBar、中栏 Step Pills、论文↔证据视图分离、AI 初判/人工最终判断的 Reviewer Panel、前端 `review_approved` 状态层(审核≠晋升)。

**Architecture:** EvidenceCenterPage 改为页面级三栏 grid;右栏为动态插槽(随模块切换:Task Summary/Paper Detail/Candidate Summary/Reviewer Panel/Promotion Impact);审核通过写 sessionStorage `evidence-center.review-approved.<targetId>`,晋升模块读取为待晋升,仅「确认晋升」调 attach。不改后端。

**Tech Stack:** React 18 + TS + Vitest/RTL + 现有自研路由/Context。

## Global Constraints

- 不改后端(Evidence 生命周期/公式/批量逻辑/Paper Library API)
- 三栏 grid:`230px minmax(620px,1fr) 370px`;页面高度 `calc(100vh - appHeader)`;三栏独立滚动
- 论文库模块全宽 + Drawer(骨架例外)
- 右栏始终回答"当前模块最重要的决策";Primary 按钮只保留当前步骤主操作
- 证据候选右栏 = 候选摘要,禁 Reviewer Confidence/Direction/attach
- 人工审核右栏 = Reviewer Panel,「审核通过/驳回」不调 attach
- 证据晋升 = 唯一 attach 入口(「确认晋升」调 POST /api/ontology/evidence/attach)
- 文案:「确认入库」→「确认晋升」;审核模块按钮为「审核通过」
- EvidenceReviewModal 保持 26 行跳转壳,不再出现业务 UI
- 复用现有组件(ClaimPanel/PassageEvidenceCard/CoveragePanel/ReviewerDecisionPanel/ConfidencePreview),不重写成熟逻辑

---

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

### Task S2: 证据候选模块重构(三栏 + 论文↔证据视图分离 + 右栏候选摘要)

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx`(大改:Claim chips/搜索三层/Paper 卡分层/Evidence View/移除右侧 Reviewer)
- Create: `frontend/src/pages/evidence-center/components/CandidateSummary.tsx`(右栏候选摘要)
- Create: `frontend/src/pages/evidence-center/components/ClaimView.tsx`(Claim 单行突出 + Component Chips,从 ClaimPanel 提取重排)
- Create: `frontend/src/pages/evidence-center/components/PaperEvidenceView.tsx`(Evidence View:← 返回论文列表 + Paper Summary + Claim Coverage + Passages)
- Modify: `frontend/src/pages/evidence-center/components/PaperCard.tsx`(信息分层:标题/citation/匹配/标签行/操作行)
- Test: `EvidenceCandidatesModule.test.tsx`(扩展)+ `PaperEvidenceView.test.tsx`

**行为:**
- 中栏:ClaimView → 搜索区三层(Query/Filter/Batch)→ PaperCard 列表 → (点「查看证据候选」)PaperEvidenceView
- PaperCard 操作:[查看详情](Drawer)/[加入提取](checkbox)/[排除];提取后 AI 判断+coverage+核验数+[查看证据候选]
- PaperEvidenceView:顶部 `← 返回论文列表`;Paper Summary;Claim Coverage(组件表 ✓/○ + 4/5);候选佐证原文(PassageEvidenceCard;reason/semantic confidence 低层级;paragraph_id/verification 进「详细信息」折叠)
- 右栏 CandidateSummary:当前 Claim / 找到论文 N / AI 提取 N / 已核验 N / Coverage / 模型判断 / [进入人工审核](openTarget review)
- 移除候选模块中的 Reviewer 修改控件

**测试:** Claim chips;搜索三层;PaperCard 分层;查看证据候选切换 + 返回;右栏无 Reviewer Confidence/Direction 控件;进入人工审核跳转

**提交:** `feat(evidence-center): 证据候选三栏重构 + 论文证据视图分离`

---

### Task S3: 人工审核模块重构(Reviewer Panel 升级 + review_approved 前端状态)

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceReviewModule.tsx`(布局对齐三栏;审核通过/驳回逻辑)
- Modify: `frontend/src/pages/evidence-center/components/ReviewerDecisionPanel.tsx`(升级:AI 初判区/分隔线「人工最终判断」/置信度影响区 Current-Reviewer-Rule-Final)
- Create: `frontend/src/pages/evidence-center/components/ReviewStatusStore.ts`(review_approved 状态读写:sessionStorage `evidence-center.review-approved.<targetId>` = {status: 'review_approved'|'rejected', at, direction, confidence, note};纯函数)
- Test: `EvidenceReviewModule.test.tsx`(扩展:审核通过写入状态/驳回写入;按钮文案「审核通过/驳回证据」)+ `ReviewStatusStore.test.ts`

**行为:**
- 右栏:标题「人工审核」→ AI 初判(模型方向+coverage)→ 分隔线「人工最终判断」→ 方向(支持/部分支持/矛盾/混合/不采用)/等级/置信度 slider+input/备注 → 「置信度影响」(Current/Reviewer/Rule cap/Final)→ sticky 底部 [驳回证据][审核通过]
- 审核通过:写 ReviewStatusStore(review_approved)+ 清候选 draft?不——保留 draft 供晋升读取;队列状态 → 前端标记
- 驳回:写 rejected
- 不调 attach

**测试:** AI 初判展示;人工判断区独立;置信度影响计算;审核通过写 store;驳回写 rejected;无 attach 调用断言

**提交:** `feat(evidence-center): 人工审核三栏重构 + review_approved 前端状态`

---

### Task S4: 证据晋升模块重构(待晋升来自 review_approved + 右栏晋升影响)

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidencePromotionModule.tsx`(待晋升读取 ReviewStatusStore;右栏晋升影响;退回人工审核)
- Create: `frontend/src/pages/evidence-center/components/PromotionImpact.tsx`(KG 当前/晋升后/Evidence 新增/Passages 新增/状态 + sticky [退回人工审核][确认晋升])
- Test: `EvidencePromotionModule.test.tsx`(扩展:待晋升来自 review_approved;退回人工审核清除状态;确认晋升仍唯一 attach)

**行为:**
- 待晋升组 = ReviewStatusStore 中 review_approved 的对象(读 draft + store)
- 中栏:选中项完整审核结果(Claim/Paper/Coverage/Reviewer decision/Confidence)
- 右栏 PromotionImpact:KG 当前(preview 或 draft)/晋升后(preview.final)/Evidence 新增 1/Passages 新增 N/状态 human_verified;[退回人工审核](清除 store,openTarget review)[确认晋升](attach + 清 store + 清 draft + 标记任务完成——S4 沿用 S1 已修的 completePaperEvidenceTaskItem)
- 已晋升/已失效保持 listPaperEvidence

**测试:** 待晋升列表来自 store;退回清除;确认晋升 attach 调用 + 状态清理;唯一 attach 断言(模块内无其他 attach)

**提交:** `feat(evidence-center): 证据晋升三栏重构 + 待晋升状态流`

---

### Task S5: 佐证任务右栏 Task Summary + 论文库全宽 + 视觉收尾

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`(右栏 Task Summary:任务状态/进度/统计/操作)
- Modify: `frontend/src/pages/evidence-center/modules/PaperLibraryModule.tsx`(全宽布局适配骨架例外)
- Modify: `frontend/src/styles.css`(三栏 grid/ContextBar/StepPills/PaperCard 分层/divider 样式;减少 border)
- Test: 回归(两模块测试适配布局断言)

**行为:**
- 佐证任务:中栏任务列表;右栏选中任务 Summary(状态/进度 total/processed/awaiting/failed/操作:开始处理/打开)
- 论文库:全宽列表 + Detail Drawer(骨架隐藏左右栏)
- 视觉收尾:section spacing + subtle divider;Primary 按钮收敛

**提交:** `feat(evidence-center): 佐证任务右栏摘要 + 论文库全宽 + 视觉收尾`

---

### Task S6: 全量回归

**Files:** 无新增
**行为:** 前端 `npx vitest run` 全绿 + `npm run build`;后端 `pytest tests/test_paper_evidence*.py tests/test_paper_library_api.py tests/test_paper_retrieval_phase2.py -q` 全绿;确认 EvidenceReviewModal 仍为跳转壳(无业务 UI);确认 review_approved 状态在刷新后保留(sessionStorage)

**提交:** 如无修复则不提交;有修复则单独 commit

---

## Self-Review 记录

- **Spec 覆盖**:§11 三栏(S1)/§12 ContextBar(S1)/§13 StepPills(S1)/§14 候选重构(S2)/§15 审核重构+review_approved(S3)/§16 晋升重构(S4)/§17 视觉(S5)/§18 测试(S6)✓
- **约束**:不改后端✓;论文库全宽例外(S5)✓;审核≠晋升(S3 store + S4 attach)✓
- **类型一致性**:ReviewStatusStore 的 key `evidence-center.review-approved.<targetId>` 与 draft key `evidence-center.review-draft.<targetId>` 并行;ReviewerDecisionPanel props 沿用(S3 扩展不改签名);PaperCard 分层不改变 props 接口
