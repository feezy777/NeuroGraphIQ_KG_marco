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

