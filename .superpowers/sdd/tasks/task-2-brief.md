### Task 2: 物理迁移 evidence-workbench 组件到 evidence-center/components

**Files:**
- Move(全部 `git mv`): `frontend/src/pages/data-center/evidence-workbench/{ClaimPanel,PassageEvidenceCard,CoveragePanel,ReviewerPanel,AttachDialog,CreateBatchTaskDialog,claimCoverage,types}.tsx|ts` → `frontend/src/pages/evidence-center/components/`
- Modify: 所有被移动文件的 import 路径(相对路径不变,若跨目录引用 data-center 的 api 则改 `../../../api/endpoints`)
- Modify: `frontend/src/pages/data-center/EvidenceReviewModal.tsx`(移动后 import 改为新路径,保持临时可用)
- Test: `frontend/src/pages/data-center/EvidenceReviewModal.test.tsx`(保持通过)

**Interfaces:**
- Produces(新路径): `frontend/src/pages/evidence-center/components/types.ts` 导出 `WorkbenchPassage`/`Direction`/`EvidenceLevel`/`QueueEntry`/`WorkbenchDraft` 等;`claimCoverage.ts` 导出 `computeTmpCoverage`/`aggregateTmpDirection`

- [ ] **Step 1: git mv 八个文件**

```bash
cd frontend/src/pages
mkdir -p evidence-center/components
git mv data-center/evidence-workbench/ClaimPanel.tsx evidence-center/components/ClaimPanel.tsx
git mv data-center/evidence-workbench/PassageEvidenceCard.tsx evidence-center/components/PassageEvidenceCard.tsx
git mv data-center/evidence-workbench/CoveragePanel.tsx evidence-center/components/CoveragePanel.tsx
git mv data-center/evidence-workbench/ReviewerPanel.tsx evidence-center/components/ReviewerPanel.tsx
git mv data-center/evidence-workbench/AttachDialog.tsx evidence-center/components/AttachDialog.tsx
git mv data-center/evidence-workbench/CreateBatchTaskDialog.tsx evidence-center/components/CreateBatchTaskDialog.tsx
git mv data-center/evidence-workbench/claimCoverage.ts evidence-center/components/claimCoverage.ts
git mv data-center/evidence-workbench/types.ts evidence-center/components/types.ts
```

- [ ] **Step 2: 修复引用**

- `EvidenceReviewModal.tsx` 顶部 import 的 `./evidence-workbench/...` 改为 `../evidence-center/components/...`
- 移动后文件内部的相对 import(如 `../../../api/endpoints`)检查并修正为 `../../../api/endpoints`(evidence-center/components 深度 = pages/evidence-center/components → api 在 src/api,路径 `../../../api/endpoints` 正确)
- `ReviewerPanel.tsx` 引用 `./types` → 不变(同目录)

- [ ] **Step 3: 运行前端测试确认移动无损**

Run: `cd frontend && npx vitest run src/pages/data-center/EvidenceReviewModal.test.tsx`
Expected: PASS(24 passed)——证明移动未破坏行为

- [ ] **Step 4: 提交**

```bash
git add -A frontend/src/pages
git commit -m "refactor(evidence): 迁移 evidence-workbench 组件到 evidence-center/components"
```

---

