# V2 Final Review Fix Report

## 2026-08-10 — V2 终审 2 个 Important 修复

Commit: `f6cf2e4` — fix(evidence-center): 多论文草稿跨论文累计 + 审核通过零选中禁用

### Finding 1: 多论文草稿覆盖(违反「多论文多片段混合审核」)

- 文件: `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx`
- 根因: auto-draft effect 只从当前查看的论文(`evidencePaper`)计算 passages 并写 per-target draft key,在论文 A 选片段后再看论文 B 选片段,A 的选择被 B 覆盖;但右栏 `selectedPassages: selectedHashes.size` 跨所有论文求和 → 「进入人工审核(2)」但草稿仅 1 条。
- 修复: draft effect 改为**跨论文累计** —— 遍历全部已提取论文(`candidates + manualResults`),收集 `selectedHashes` 命中的片段(hash 含 paperId 前缀,`${paperId}-${i}-${passage}`,可反查归属论文),按 hash 去重后写入同一份草稿;元数据(modelDirection/modelAssessment/paperTitle/pmid)取第一篇贡献片段的论文;effect 不再依赖 `evidencePaper`,列表视图下选择同样落盘。
- 草稿删除保护保留: `draftWrittenRef` 仍区分「用户清空选择」与「尚未选择」 —— 仅当先前为本 target 写入过草稿且全部选中被清空时才删除,不误删审核模块已存在的草稿。

### Finding 2: 审核通过零选中也可点

- 文件: `frontend/src/pages/evidence-center/components/ReviewerDecisionPanel.tsx`
- 根因: 「审核通过」按钮无 guard,全部取消勾选后仍可写入 `review_approved`,在晋升模块产生 `canPromote=false` 卡死项。
- 修复: 镜像候选模块 `CandidateSummary` 的 guard —— `selectedCount === 0` 时 `disabled` + `title="请先勾选已核验的候选片段"`;驳回按钮不受影响。

### 测试与验证

- 新增/更新断言: `EvidenceCandidatesModule.test.tsx`(多论文混合审核累计、取消一篇保留另一篇、全部清空删除草稿)+ 新建 `ReviewerDecisionPanel.test.tsx`(零选中禁用/不触发 onApprove/有选中启用)。
- `npx vitest run src/pages/evidence-center/`: 16 files, 138 tests passed
- `npx vitest run`(全量): 19 files, 152 tests passed
- `npx tsc --noEmit`: 0 errors
