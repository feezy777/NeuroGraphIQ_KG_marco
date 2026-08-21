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

