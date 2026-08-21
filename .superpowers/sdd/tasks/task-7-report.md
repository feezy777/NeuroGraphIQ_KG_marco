# Task 7 Report: 证据候选模块(EvidenceCandidatesModule)

## Status: DONE

Commit: `9d645bc` on `codex/ontology-evidence` — "feat(evidence): 证据候选模块(EvidenceCandidatesModule)"

## Files Changed (committed, 5 files)

| File | Change |
|------|--------|
| `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx` | NEW — 证据候选模块 |
| `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx` | NEW — 9 个测试 |
| `frontend/src/pages/evidence-center/components/candidatePassages.ts` | NEW — 共享转换函数 `candidatePassagesToWorkbench`(从 EvidenceReviewModal 提取) |
| `frontend/src/pages/data-center/EvidenceReviewModal.tsx` | 删除内联 `candidatePassagesToWorkbench`,改 import 共享模块(diff 仅 1 增 29 删) |
| `frontend/src/styles.css` | 追加 `.evidence-candidates-*` / `.evidence-candidate-paper` 样式(约 95 行) |

## Implementation Summary

- **布局**:`<div className="evidence-candidates">` = 左 240px 候选队列(任务 items 转 QueueEntry,含 label/status/preprocess_outcome/model_direction,点击 `openTarget(tt,tid,'candidates')` 切换)+ 主区。
- **数据加载**:`listPaperEvidenceTaskItems(taskId, {limit: 100})` → items → `setQueue`(同步到 context,供 T8/T9 复用);当前 target 的 `getEvidenceTarget` → ClaimPanel;无 target 时自动选中第一个 item 写入 URL。
- **Candidate Paper 卡**:title / journal·year·PMID、model_direction 徽章(DIRECTION_LABEL + ok/warn/bad 色调)、coverage_summary 覆盖度百分比、片段数、已核验数(source_verified 计数)、`fulltext_fetched === false` 时显示「仅摘要」。
- **每卡操作**:
  - 查看候选证据 → 展开片段列表(每片段:选择复选框 / direction / scope / 已核验标记 / 原文文本)
  - 加入人工审核(勾选片段后启用)→ 写 `sessionStorage['evidence-center.review-draft.<targetId>']` = `{passages, modelDirection, modelAssessment, paperTitle, pmid}` → `openTarget(tt, tid, 'review')`
  - 排除 → 前端隐藏(Set 状态,paper_id/pmid 作 key)
  - 重新提取 → `extractSelectedPaperEvidence` 按 pmid 重提,就地更新任务 item / 手动结果
- **手动提取兜底**(task items 为空时):searchPaperEvidence 检索式输入 + 多选论文 + extract-selected,结果复用候选卡。mode 按 target_type(connection/projection → existence,其余 function)。
- **禁止项合规**:无 attach 按钮、无 confidence 修改控件、无「确认论文证据/确认入库/保存草稿」文案(测试断言)。

## Tests

- 新增 9 个测试,全部通过(`npx vitest run src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx`):
  1. 左队列渲染(label + 状态标签 + listPaperEvidenceTaskItems 调用参数)
  2. ClaimPanel 渲染 claim_text + components + granularity
  3. 候选卡渲染 title / model_direction / 覆盖度 / 片段数 / 已核验数
  4. 展开片段列表 + 已核验标记
  5. 加入人工审核 → hash 含 `module=review` + sessionStorage draft 内容断言(passages/modelDirection/modelAssessment/paperTitle/pmid)
  6. 排除 → 卡片移除 + 空态提示
  7. 重新提取 → 触发 `extractSelectedPaperEvidence`(断言 body papers.pmid)+ 片段数 2→3、已核验 1→2
  8. 禁止项:无 attach/confirm 文案与 `ew-attach` 控件
  9. items 为空 → 手动检索入口渲染,「检索」触发 searchPaperEvidence
- 全量:`npx vitest run` → **8 files / 58 tests passed**
- `tsc -b` 0 错误;`npm run build` 通过(仅有预先存在的 chunk-size / dynamic-import 警告)

## Notes / Concerns

1. **TDD**:测试先行(RED:模块不存在)→ 实现(GREEN:9/9)。
2. 测试中途两处修正:审核按钮带计数后缀(改 `getByRole('button', {name:/加入人工审核/})` 避免与提示文案重复匹配)。
3. `EvidenceCandidatesModule` 未接入 `EvidenceCenterPage.tsx`(页内接线由后续任务处理,本任务未触碰该文件)。
4. 队列 `evidenceCount` 取 candidate_papers 数量(候选视角),与 review 模块的正式证据计数语义不同,属有意为之。

## Task 7 Review 修复(2026-08-10, commit 58e73ad)

- **Finding 1(展开状态键不一致)**:`expanded` 与 `onToggleExpand` 原仅用 `cand.paper_id` 作键,与卡片 `key`/`reExtractBusy`/`excludedPaperIds` 的组合键 `cand.paper_id || cand.pmid` 不一致;`paper_id` 为 null 时 `null === null` 恒真导致所有无 paper_id 的卡默认展开且无法收起。已统一为组合键(两处 CandidatePaperCard 渲染:候选列表 + 手动提取结果)。
- **Finding 2(空态文案承诺不存在的入口)**:「…或使用下方手动检索入口」仅在 `items.length === 0` 时存在该入口,但文案在 `items.length > 0 && candidates.length === 0` 时渲染。已改为「当前对象暂无候选证据,可尝试重新提取或切换其他对象。」,同步更新测试断言 `/当前对象暂无候选证据/`。
- 验证:`npx vitest run src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx` → 9/9 通过;`npx tsc --noEmit` → 0 错误。
