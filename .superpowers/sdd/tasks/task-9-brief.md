### Task 9: 证据晋升模块(EvidencePromotionModule)

**Files:**
- Create: `frontend/src/pages/evidence-center/modules/EvidencePromotionModule.tsx`
- Create: `frontend/src/pages/evidence-center/components/PromotionDialog.tsx`(git mv AttachDialog 改名,文案「确认晋升」)
- Create: `frontend/src/pages/evidence-center/components/EvidenceDetailDrawer.tsx`
- Test: `frontend/src/pages/evidence-center/modules/EvidencePromotionModule.test.tsx`

**Interfaces:**
- Consumes: `useEvidenceCenter().state`;sessionStorage draft;`attachPaperEvidencePreview`/`attachPaperEvidence`/`listPaperEvidence`/`rollbackPaperEvidence`;`PromotionDialog` props 沿用 AttachDialog(`{open, targetLabel, claimText, paper, passages, components, direction, preview, busy, onConfirm, onClose}`)
- Produces: 分组(待晋升[来自 draft 且已审核]/已晋升[listPaperEvidence]/已失效[invalidated]);`EvidenceDetailDrawer` props `{ open, evidence, onClose, onRollback }`

- [ ] **Step 1: 写失败测试**

mock `listPaperEvidence`(返回 human_verified 一条 + invalidated 一条)+ sessionStorage draft;断言:
1. 「待晋升」组显示 draft 的 Claim/Paper/Reviewer Decision/当前 confidence/预计后 confidence(preview mock)
2. 「确认晋升」→ `attachPaperEvidence` 调用(body 含 direction/reviewer_confidence/passages)+ 文案为「确认晋升」
3. 晋升成功后列表刷新(listPaperEvidence 再调用)
4. EvidenceDetailDrawer 打开显示 evidence 详情;「回滚」→ `rollbackPaperEvidence` 调用
5. 已失效组渲染 invalidated 记录

- [ ] **Step 2: 实现模块**

加载:待晋升 = sessionStorage draft(有 direction 且 selectedPassages 非空);已晋升/已失效 = `listPaperEvidence({target_type, target_id, limit: 50})` 按 `invalidated_at` 分组。
晋升动作:`attachPaperEvidencePreview`(预览)→ PromotionDialog 确认 → `attachPaperEvidence` → 刷新列表 + 清 draft + 更新 queue。
`EvidenceDetailDrawer`:evidence 字段展示(claim snapshot/paper/coverage/reviewer decision/passages/confidence 调整状态)+ 回滚按钮(`rollbackPaperEvidence(evidenceId, reason)` 用 ConfirmDialog 输入原因)。
`PromotionDialog`:AttachDialog 全文替换「确认入库」→「确认晋升」,其余不变。

- [ ] **Step 3: 测试通过 + build + 提交**

---

