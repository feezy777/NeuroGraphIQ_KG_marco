### Task 8: 人工审核模块(EvidenceReviewModule)

**Files:**
- Create: `frontend/src/pages/evidence-center/modules/EvidenceReviewModule.tsx`
- Create: `frontend/src/pages/evidence-center/components/ReviewerDecisionPanel.tsx`(从 ReviewerPanel 拆出决策区 + ConfidencePreview)
- Create: `frontend/src/pages/evidence-center/components/ConfidencePreview.tsx`
- Modify: `frontend/src/pages/evidence-center/components/ReviewerPanel.tsx`(保留旧导出兼容?→ 删除,由 ReviewerDecisionPanel 替代)
- Test: `frontend/src/pages/evidence-center/modules/EvidenceReviewModule.test.tsx`

**Interfaces:**
- Consumes: sessionStorage draft(`evidence-center.review-draft.<targetId>`);`getEvidenceTarget`;`attachPaperEvidencePreview`(endpoints:5471);`translateEvidenceText`;`validatePassageSelection`;`saveTaskItemDraft`;`useEvidenceCenter().state/openTarget`
- Produces: `ReviewerDecisionPanel` props: `{ direction, modelDirection, onDirectionChange, evidenceLevel, onEvidenceLevelChange, confidence, onConfidenceChange, note, onNoteChange, selectedCount, preview, previewBusy }`(与旧 ReviewerPanel 相同签名,渲染时 AI 推荐灰字)

- [ ] **Step 1: 写失败测试**

mock endpoints(`getEvidenceTarget`/`attachPaperEvidencePreview`/`translateEvidenceText`);断言:
1. 从 sessionStorage draft 恢复 passages 并渲染 PassageEvidenceCard(含「AI 推荐」灰字标注 modelDirection)
2. ReviewerDecisionPanel 方向修改 → attach-preview 触发(debounce 350ms,用 `waitFor`)
3. 翻译按钮 → translateEvidenceText 调用并显示译文
4. 「返回证据候选」→ URL `module=candidates` 且 draft 仍保留(重新进入 review 恢复)
5. AI 推荐与人工确认视觉:`modelDirection` 显示「AI 推荐:支持」,人工方向 radio 独立

- [ ] **Step 2: 实现模块**

`EvidenceReviewModule.tsx` 布局:`<div className="evidence-review">` = 左/中(ClaimPanel + 当前 Paper 信息 + PassageEvidenceCard 列表 + CoveragePanel)+ 右 380px `ReviewerDecisionPanel`。
draft 恢复/保存:`useEffect` 监听 `state.targetId` 读 sessionStorage;变更时 debounce 写回;「返回证据候选」`openTarget(tt, tid, 'candidates')`。
置信度预览:350ms debounce 调 `attachPaperEvidencePreview`(复用原逻辑)。
`ReviewerDecisionPanel` = 原 ReviewerPanel 的内容,AI 推荐行(`modelDirection` 前加「AI 推荐:」灰字)+ `ConfidencePreview`(current → final + 公式 + cap + block_reasons)。

- [ ] **Step 3: 测试通过 + build + 提交**

---

