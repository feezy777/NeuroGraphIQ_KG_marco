# Task S4 Report: 证据晋升模块三栏重构 + 待晋升状态流(review_approved)

## Status: DONE

## 变更概览

### 1. 待晋升组数据源改为 ReviewStatusStore(`modules/EvidencePromotionModule.tsx`)
- 待晋升列表 = `listReviewApproved().filter(r => r.status === 'review_approved')`(扫描 sessionStorage 前缀),不再从「当前目标 draft 有无」推导。
- 选中项默认跟随当前对象(`state.targetId`),否则取列表首个;点击待晋升行切换选中项(行高亮 `evidence-promotion-row-selected`)。
- 待晋升行摘要:对象 label(队列匹配,否则 targetId)/ 人工方向 / 证据等级 / 置信度 / 审核时间(meta.at)。
- 中栏 = 选中项**完整审核结果**(复用现有渲染):ClaimPanel + 论文块 + **CoveragePanel**(`computeTmpCoverage`/`aggregateTmpDirection` 复用)+ Reviewer 决策(人工方向/证据等级/置信度/备注/所选片段/预计后置信度)+ 审核状态行(`review_approved · at`)。
- 已晋升/已失效保持 `listPaperEvidence`(当前对象,按 `invalidated_at` 分组),回滚链路不变。
- 无 target 时仍渲染待晋升组 + 「请先从…进入一个目标对象」空态(EvidenceCenterPage 接线测试兼容)。

### 2. 右栏 PromotionImpact(`components/PromotionImpact.tsx`,新建)
- 经 Context 推送(`promotionImpact` 状态,与 S3 `reviewDecision` 同模式),`RightPanel` promotion 分支渲染;无待晋升/无草稿时占位「晋升确认」。
- 字段:人工方向 / KG 当前置信度 / 晋升后置信度(含 cap 上限)/ Evidence 新增 +1 / Passages 新增 +N(selectedPassages 数)/ 状态 `human_verified`。
- 置信度影响:preview 可用时取服务端 `current/final/cap`;否则本地 `computeConfidenceImpact`(复用 `components/confidenceImpact.ts` 公式与钳制)。
- sticky 底部(`ew-sticky-actions`):`[退回人工审核]`(次要)`[确认晋升]`(primary,唯一 attach 入口,`canPromote=false` 时禁用)。

### 3. 确认晋升流程(唯一 attach)
- 保持原 attach 链路(PromotionDialog 确认 → `attachPaperEvidence`)→ 成功后:`clearReviewStatus` + 清 draft + 刷新待晋升与已晋升/已失效列表 + queue 标记 `completed` + `completePaperEvidenceTaskItem`(失败静默,沿用 S1 修复)。
- 中栏卡片不再有确认按钮 —— 全页仅右栏一个「确认晋升」触发点。

### 4. 退回人工审核
- `clearReviewStatus(targetId)` + 清 draft + `openTarget(targetType, targetId, 'review')`,待晋升列表即时刷新。

### 5. 配套
- `ReviewStatusStore.ts`:`saveReviewStatus` 新增可选 `targetType`(审核模块写入,晋升模块据此 attach/退回跳转;缺省不写入,向后兼容)。
- `EvidenceReviewModule.tsx`:提交审核状态时携带 `state.targetType`。
- `EvidenceCenterContext.tsx`:`promotionImpact` 状态;并将 `gotoModule/openTask/openTarget/selectPaper` 改为 `useCallback` 稳定引用。
- `styles.css`:`evidence-promotion-impact`(ew-promo-field 行布局)+ `evidence-promotion-row-selected` 高亮。

## 关键修复:无限重渲染(worker 崩溃/挂起)
- 现象:渲染「待晋升 + 右栏 PromotionImpact」时 vitest worker 无限循环(CPU 打满,`Worker exited unexpectedly`)。
- 根因:`openTarget` 等导航回调是 context value 内的**内联箭头**,随 context 每次变化重建;晋升模块 `handleReturnToReview` 依赖 `openTarget` → `promotionImpact` memo 每渲染重建 → 推送 effect 每渲染 `setPromotionImpact` → context 变化 → 循环。S3 未触发是因为其回调不依赖 context 回调。
- 修复:context 导航回调全部 `useCallback` 稳定化(根因修复,对所有消费方更正确)。
- 另修复:晋升成功后选中项复位时,草稿加载 effect 不再清空成功消息(改为用户点击行时清消息)。

## 测试
- 新建 `PromotionImpact.test.tsx`(7 个):preview 优先 / 本地公式 + 钳制(supports cap 0.85)/ 弱证据不改变 / contradicts 不修改 / 字段(方向/Evidence+1/Passages+N/状态)/ 按钮回调与禁用 / previewBusy。
- 扩展 `EvidencePromotionModule.test.tsx`(13 个):待晋升来自 store(排除 rejected)、选中项完整审核结果(含 Coverage)、右栏 PromotionImpact 字段、多待晋升项点击切换(中栏+预览跟随)、确认晋升 body 断言、晋升后清 status+draft+刷新、completePaperEvidenceTaskItem(含标记失败不阻断、无 task_id 不调用)、**唯一 attach 断言**(打开弹窗不 attach、一次晋升只调一次)、退回人工审核清状态跳 review、已晋升回滚、已失效只读、禁止项。
- 扩展 `ReviewStatusStore.test.ts`(+1:targetType 写入/缺省不写)。
- **运行结果**:`evidence-center` 127 通过(基线 114);全量 `npx vitest run` 141 通过(基线 114+27 新增);`npm run build` 成功(仅既有 chunk 体积 warning)。

## 遗留说明
- 待晋升项在缺少 draft(如被外部清理)时,右栏显示占位、中栏提示「没有可晋升的审核草稿」,确认按钮禁用——正常路径(审核通过必落 draft)不受影响。
