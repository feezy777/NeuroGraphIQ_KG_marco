# Task 8 Report: 人工审核模块(EvidenceReviewModule)

## Status: DONE

Commit: `36432b7` on `codex/ontology-evidence` — "feat(evidence): 人工审核模块(EvidenceReviewModule)"

## Files Changed (committed, 5 files)

| File | Change |
|------|--------|
| `frontend/src/pages/evidence-center/modules/EvidenceReviewModule.tsx` | NEW — 人工审核模块(约 330 行) |
| `frontend/src/pages/evidence-center/modules/EvidenceReviewModule.test.tsx` | NEW — 8 个测试 |
| `frontend/src/pages/evidence-center/components/ReviewerDecisionPanel.tsx` | NEW — 决策区(从旧 ReviewerPanel 拆出,props 签名相同 + AI 推荐视觉 + ConfidencePreview) |
| `frontend/src/pages/evidence-center/components/ConfidencePreview.tsx` | NEW — `{ preview }` 展示 current → final + 公式 + cap + block_reasons |
| `frontend/src/styles.css` | 追加 `.evidence-review-*` / `.ew-ai-recommend` / `.ew-dir-chip*` 样式(53 行) |

旧 `ReviewerPanel.tsx` **保留未改** — `frontend/src/pages/data-center/EvidenceReviewModal.tsx` 仍在 import 它,删除会破坏构建;`ReviewerDecisionPanel` 以同签名新组件替代(简报允许「保留旧导出兼容」)。

## Implementation Summary

- **布局**:`<div className="evidence-review">` = 左/中 `evidence-review-main`(ClaimPanel + 当前论文信息卡 title/pmid/doi + PassageEvidenceCard 列表 + CoveragePanel)+ 右 `evidence-review-side` 固定 380px(ReviewerDecisionPanel + 操作按钮行)。
- **草稿恢复/保存**:
  - 挂载(targetId 变化)时读 `sessionStorage['evidence-center.review-draft.<targetId>']`,恢复 passages/modelDirection/modelAssessment/paperTitle/pmid/doi/translations/reviewerDirection/reviewerEvidenceLevel/reviewerConfidence/note;已核验片段默认全选(`selectedHashes`)。
  - 变更 debounce 500ms 写回(内容为空时跳过,避免污染空草稿);目标切换时旧 timer 由 effect cleanup 清除。
- **置信度预览**:direction/confidence/selectedHashes/passages/pmid 变化后 debounce 350ms 调 `attachPaperEvidencePreview`,body 与旧逻辑一致(`target_type/target_id/pmid/direction/reviewer_confidence/passages[]` 含 source_verified/supported_components);无 pmid 或无已选片段时跳过;abortRef 取消旧请求,`AbortError` 不显示错误消息。
- **片段操作**(全部复用 PassageEvidenceCard props):勾选(checkbox 由卡片在 `source_verified=false` 时禁用)、evidence_level 修改、supported_components 修改、翻译(`translateEvidenceText({text})` → 写入 translations[hash])、复制、展开上下文、重新截取(`validatePassageSelection` 通过后以 normalized_selection 替换原文并置 source_verified=true)。
- **CoveragePanel**:`computeTmpCoverage` + `aggregateTmpDirection`(selectedPassages 非空时显示)。
- **操作按钮**:
  - 「返回证据候选」→ `openTarget(tt, tid, 'candidates')`,draft 保留在 sessionStorage(重新进入 review 可恢复)。
  - 「保存草稿」→ 立即写 sessionStorage + 若 context queue 中有匹配 target 的 `taskItemId`(T7 已 setQueue 供本模块复用)调 `saveTaskItemDraft(itemId, draft, 0)`,显示 保存中/已保存/保存失败;无 taskItem 时提示「已保存在本地」。
- **AI 推荐视觉**:`ReviewerDecisionPanel` 中 `modelDirection` 渲染为灰字徽章 `.ew-ai-recommend`「AI 推荐：支持」;人工方向 5 个 radio 为独立 chip(`.ew-dir-chip`),当前选中 `.ew-dir-chip-active` 高亮(primary 蓝底);`not_found/contradicts/mixed` 时显示方向说明文案,`supports/partial` 时渲染 ConfidencePreview。
- **禁止项合规**:无 Europe PMC 搜索控件、无 attach/「确认论文证据/确认入库」控件(测试断言)。

## Tests

- 新增 8 个测试,全部通过(`npx vitest run src/pages/evidence-center/modules/EvidenceReviewModule.test.tsx`):
  1. sessionStorage draft 恢复 → 渲染 PassageEvidenceCard(已核验/未核验、AI 推荐灰字、未核验 checkbox 禁用)
  2. 方向修改 → `attachPaperEvidencePreview` 触发(debounce 350ms,断言 direction=contradicts + body passages)
  3. 翻译按钮 → `translateEvidenceText({text})` 调用并显示译文
  4. 「返回证据候选」→ hash `module=candidates` 且 draft 保留,重新进入 review 恢复
  5. AI 推荐视觉:`ew-ai-recommend` 文本 + 5 个 radio + 选中 chip 高亮
  6. 禁止项:无搜索框 / 无 Europe PMC / 无 attach 控件
  7. 保存草稿:写 sessionStorage(reviewerDirection 等字段)+ 有 taskItemId 时调 `saveTaskItemDraft`(QueueSeeder 注入 context queue)
  8. 重新截取 → `validatePassageSelection` 调用且通过后替换原文
- 全量:`npx vitest run` → **9 files / 66 tests passed**
- `npm run build`(含 `tsc -b`)→ 通过,0 TS 错误(仅有预先存在的 chunk-size 警告)

## TDD 过程

1. RED:先写测试(8 个),模块不存在 → 运行失败(import 解析错误)。
2. GREEN:实现 ConfidencePreview / ReviewerDecisionPanel / EvidenceReviewModule + CSS → 6/8 通过。
3. 修两处测试本身的问题:`attachPaperEvidencePreview` 实际以 `(body, signal)` 两参调用,`toHaveBeenLastCalledWith` 需补 `expect.anything()` 匹配 signal;`getByLabelText` 返回 input 元素(textContent 为空),改断言 label chip 的 className 高亮。
4. 实现侧一处自审修复:预览请求 abort 时旧 promise 的 catch 会误报「预览失败」,增加 `AbortError` 判断跳过。

## Notes / Concerns

1. **saveTaskItemDraft 触发条件**:简报写「若有 taskId 调 saveTaskItemDraft」,但接口签名需要 itemId;本实现从 context queue(T7 同步,含 taskItemId)取匹配目标项的 taskItemId 后调用,无 taskItemId 时仅写本地并提示。深链直达 review 且未经过候选模块时 queue 为空,后端保存会跳过(属预期,正常流转 tasks→candidates→review 时可用)。
2. **模块未接入 `EvidenceCenterPage.tsx`**:与 T7 相同,页内接线由后续任务处理,本任务未触碰该文件。
3. **draft 结构兼容**:读写均保留 T7 写入的 `{passages, modelDirection, modelAssessment, paperTitle, pmid}` 字段,并追加 `doi/translations/reviewerDirection/reviewerEvidenceLevel/reviewerConfidence/note`(旧字段缺失时使用默认值,向后兼容)。
4. 旧 `ReviewerPanel` 与新的 `ReviewerDecisionPanel` 并存(前者仅 EvidenceReviewModal 使用);如需消除重复可后续让旧面板复用新组件。

## 评审修复 (2026-08-10)

- **Fix (Important)**: `frontend/src/styles.css` `.ew-ai-recommend` 将 `color: var(--muted)` 改为 `color: var(--text-muted)`(`--muted` 全前端未定义,正确 token 是 styles.css:14 的 `--text-muted`;未定义 var 回退为继承深色导致灰字变黑字)。
- **同类检查**:grep 本提交(36432b7)新增行中的 `var(--` 引用,涉及 `--border`/`--white`/`--primary`/`--text`/`--text-muted` 均已定义,`--muted` 为唯一未定义引用,无其他遗漏。
- **验证**:`npx vitest run src/pages/evidence-center/modules/EvidenceReviewModule.test.tsx` → 8/8 passed;`npx tsc --noEmit` → 无错误。
- **Commit**: `7674300`
