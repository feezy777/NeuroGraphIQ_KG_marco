### Task 7: 证据候选模块(EvidenceCandidatesModule)

**Files:**
- Create: `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx`
- Test: `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx`

**Interfaces:**
- Consumes: `useEvidenceCenter().state/openTask/openTarget/queue/setQueue`;`listPaperEvidenceTaskItems`(endpoints:5592)、`getTaskItemDraft`? 候选数据用 task items 的 candidate_papers;`searchPaperEvidence`/`extractSelectedPaperEvidence`(手动提取);`getEvidenceTarget`(Claim DTO)
- Produces: 通过 `useEvidenceCenter()` 向 review 模块传递:调用 `openTarget(tt, tid, 'review')` 并写入 sessionStorage key `evidence-center.review-draft.<targetId>` 存 { passages, modelDirection, modelAssessment, paperTitle, pmid }

- [ ] **Step 1: 写失败测试**

mock `listPaperEvidenceTaskItems` 返回含 candidate_papers 的 item;断言:
1. 左队列渲染对象(label + status)
2. 主区 Claim + Components 渲染(mock `getEvidenceTarget`)
3. Candidate Paper 卡:title/model_direction/coverage/passage count/verified count
4. 「加入人工审核」→ URL 变 `module=review` 且 sessionStorage 有 draft
5. 「排除」从列表移除;「重新提取」触发 `extractSelectedPaperEvidence`(mock)

- [ ] **Step 2: 实现模块**

布局:`<div className="evidence-candidates">` = 左 240px 队列(`visibleQueue` 复用 types.QueueEntry)+ 主区(ClaimPanel + CandidatePapers 列表)。
数据加载:`listPaperEvidenceTaskItems(taskId, {limit: 100})` → queue;当前 target 的 `getEvidenceTarget` → claim;candidate 卡复用 `candidatePassagesToWorkbench`(从 EvidenceReviewModal 提取到 components/ 共享函数,Task 8 前先复制进 components/candidatePassages.ts)。

- [ ] **Step 3: 测试通过 + build + 提交**

---

