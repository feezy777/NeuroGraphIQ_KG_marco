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

